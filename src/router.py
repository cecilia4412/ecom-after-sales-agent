"""AgentRouter 核心节点：意图分析、情绪检测与实体抽取。

设计思路：
- 用一个统一的 LLM 调用同时完成「情绪判定 + 意图分类 + 实体提取」
- 让模型输出严格 JSON，避免自然语言解析带来的脆弱性
- 简单的字段级正则后处理：订单号兜底，确保 ORD-2024 这种不会被吞掉
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm import get_llm
from src.state import AgentState

# 订单号正则（形如 ORD-2024 / ORD-9999）
_ORDER_ID_PATTERN = re.compile(r"\bORD[-\s]?\d{3,6}\b", re.IGNORECASE)

# 情绪关键词（高愤怒：含明显脏话/强烈负面/威胁/催促）
_ANGRY_KEYWORDS = (
    "垃圾", "废物", "投诉", "差评", "无语", "气死", "过分",
    "妈的", "fuck", "shit", "sb", "傻逼", "滚", "骗子", "骗人",
    "等了", "十天了", "怎么还不", "再不退", "再不发货", "退款", "退钱",
)
_COMPLAINT_KEYWORDS = ("投诉", "举报", "差评", "曝光", "起诉")

# 已知品类（用于兜底匹配）
_KNOWN_CATEGORIES = ("电子产品", "服装鞋帽", "美妆护肤", "食品饮料", "家居日用")


_INTENT_PROMPT = """你是电商售后中控系统的「意图分析器」。请阅读用户最新输入，
**严格输出 JSON**，不要输出任何额外文字或 Markdown 代码块。

JSON 字段说明：
- emotion: "angry" | "calm" | "neutral"  （angry 表示用户有明显愤怒/激动情绪）
- intent: "query_order" | "refund" | "policy" | "complaint" | "chitchat" | "other"
    - query_order: 查快递/订单状态
    - refund:     申请退货/退款
    - policy:     询问退换货政策
    - complaint:  投诉/差评/曝光
    - chitchat:   普通闲聊/非业务问题
    - other:      兜底
- order_id: 字符串或 null，例如 "ORD-2024"（注意格式为 ORD-数字）
- category: 字符串或 null，已知品类有：电子产品 / 服装鞋帽 / 美妆护肤 / 食品饮料 / 家居日用
- product:  字符串或 null，用户提到的具体商品
- reason:   字符串或 null，简要描述用户诉求（如 "蓝牙耳机有杂音想退货"）

只输出 JSON，例如：
{{"emotion":"calm","intent":"refund","order_id":"ORD-2024","category":"电子产品","product":"蓝牙耳机","reason":"蓝牙耳机有杂音想退货"}}
"""


def _post_process(state: AgentState, parsed: dict) -> AgentState:
    """对 LLM 输出做后处理：兜底正则、字段归一化。"""
    updates: dict = {
        "emotion": parsed.get("emotion") or "neutral",
        "intent": parsed.get("intent") or "other",
        "order_id": parsed.get("order_id"),
        "category": parsed.get("category"),
        "product": parsed.get("product"),
        "reason": parsed.get("reason"),
    }

    # 订单号兜底：模型可能漏抽，用正则补（先查当前消息，再查历史）
    if not updates["order_id"]:
        last_user_msg = _last_user_text(state)
        m = _ORDER_ID_PATTERN.search(last_user_msg)
        if m:
            updates["order_id"] = m.group(0).upper().replace(" ", "")
        else:
            # 从对话历史中查找最近提到的订单号
            for msg in reversed(state.get("messages", [])):
                msg_type = getattr(msg, "type", "")
                if msg_type != "human":
                    continue
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                if text == last_user_msg:
                    continue  # 跳过当前消息（已查过）
                m = _ORDER_ID_PATTERN.search(text)
                if m:
                    updates["order_id"] = m.group(0).upper().replace(" ", "")
                    break

    # 品类兜底：检查最近历史消息中是否提到已知品类
    if not updates["category"]:
        last_user_msg = _last_user_text(state)
        for cat in _KNOWN_CATEGORIES:
            if cat in last_user_msg:
                updates["category"] = cat
                break

    # 关键词兜底：基于关键词的愤怒检测
    last_user_msg = _last_user_text(state)
    if updates["emotion"] != "angry":
        lower = last_user_msg.lower()
        hits = sum(1 for kw in _ANGRY_KEYWORDS if kw.lower() in lower)
        if hits >= 2:
            updates["emotion"] = "angry"

    # 投诉意图兜底
    if updates["intent"] in ("other", "chitchat", None) and any(
        kw in last_user_msg for kw in _COMPLAINT_KEYWORDS
    ):
        updates["intent"] = "complaint"

    # 路由决策
    emotion = updates["emotion"]
    intent = updates["intent"]
    order_id = updates["order_id"]

    # 情绪风控：愤怒 → 直接转人工
    if emotion == "angry" or intent == "complaint":
        updates["route"] = "escalate"
        if not updates["reason"]:
            updates["reason"] = "用户情绪激动，触发情绪风控转人工"
        return updates

    # 缺信息追问：需要订单号但没拿到 → 反问
    if intent in ("query_order", "refund") and not order_id:
        updates["route"] = "ask_info"
        updates["needs_info"] = True
        if intent == "query_order":
            updates["info_question"] = "为了帮您查询订单状态，请提供您的订单号（形如 ORD-XXXX）。"
        else:
            updates["info_question"] = "为了帮您处理退货申请，请提供您的订单号。"
        return updates

    # 工具调用：退款/查订单/政策问询
    if intent in ("query_order", "refund", "policy"):
        updates["route"] = "tools"
        return updates

    # 闲聊/兜底
    updates["route"] = "direct"
    return updates


def _last_user_text(state: AgentState) -> str:
    """取出 messages 中最后一条 HumanMessage 文本。"""
    for msg in reversed(state.get("messages", [])):
        # HumanMessage / AIMessage 都有 .content
        if getattr(msg, "type", None) == "human" or msg.__class__.__name__ == "HumanMessage":
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return ""


def _build_conversation_context(state: AgentState, max_turns: int = 6) -> str:
    """从对话历史中构建上下文摘要，帮助 LLM 理解多轮语境。"""
    messages = state.get("messages", [])
    if len(messages) <= 1:
        return ""

    # 取最近 max_turns 轮（不含当前最新一条，因为当前消息单独发送）
    history = messages[:-1]
    if not history:
        return ""

    lines = ["对话历史："]
    for msg in history[-(max_turns * 2):]:  # 每轮约 2 条消息（human + ai）
        msg_type = getattr(msg, "type", "")
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if not content:
            continue
        if msg_type == "human":
            # 截断过长的历史消息
            short = content[:120] + ("..." if len(content) > 120 else "")
            lines.append(f"  用户: {short}")
        elif msg_type == "ai":
            short = content[:200] + ("..." if len(content) > 200 else "")
            lines.append(f"  客服: {short}")

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def analyze_node(state: AgentState) -> AgentState:
    """意图分析节点：调用 LLM 抽取结构化字段，并决定路由。"""
    last_user_msg = _last_user_text(state)
    if not last_user_msg:
        return {"route": "direct", "intent": "other", "emotion": "neutral"}

    llm = get_llm(temperature=0.0)

    # 每轮重新分析：先清除上一轮的 per-turn 状态，避免情绪/路由污染
    reset: dict = {
        "emotion": "neutral",
        "intent": "other",
        "route": "direct",
        "needs_info": False,
        "info_question": "",
    }

    # 构建带上下文的分析输入
    context = _build_conversation_context(state)
    prompt_parts = [_INTENT_PROMPT]
    if context:
        prompt_parts.append(f"\n{context}\n")
    system_content = "\n".join(prompt_parts)

    resp = llm.invoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=last_user_msg),
        ]
    )
    raw = (resp.content or "").strip()

    parsed: dict = {}
    try:
        # 尝试抽取第一个 JSON 块
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
    except Exception:
        parsed = {}

    # 合并: reset 作为基底，parsed 覆盖
    result = {**reset, **_post_process(state, parsed)}
    return result


# 给 LangChain 结构化输出用的 schema（备用）
class _IntentSchema(dict):
    """占位：实际未启用，仅保留参考。"""
    pass
