"""LangGraph 工作流编排。

Graph 结构：
    START
      ↓
    analyze（意图 + 情绪 + 实体抽取）
      ↓
    ┌─────────────┬──────────────┬──────────────┐
    │             │              │              │
  escalate     ask_info        tools        direct
  (转人工)    (反问用户)      (调用工具)    (直接回复)
    │             │              │
    ↓             ↓              ↓
    END        (回到analyze    generate
                等用户补充)     ↓
                                END

特点：
- 使用 MemorySaver 支持场景B的多轮追问
- thread_id 区分不同会话
"""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.router import analyze_node
from src.state import AgentState
from src.tools import (
    ALL_TOOLS,
    check_refund_policy,
    escalate_to_human,
    get_order_status,
)


# ----------------------------------------------------------------------
# 工具节点：按状态决定调用哪些工具并填充 tool_results
# ----------------------------------------------------------------------

def tool_node(state: AgentState) -> AgentState:
    """根据 state 中已有的 order_id/category 决定调用哪些工具。

    调用策略：
    - 有 order_id → 调用 get_order_status
    - 如果 policy 也想查：调用 check_refund_policy
        - 场景A：用户明确要退货 → 同时查订单+查政策
        - 场景 query_order 只想看状态 → 不查政策
    """
    intent = state.get("intent")
    order_id = state.get("order_id")
    category = state.get("category")
    tool_results: dict[str, Any] = dict(state.get("tool_results") or {})

    # 1) 查订单状态
    if order_id and "get_order_status" not in tool_results:
        raw = get_order_status.invoke({"order_id": order_id})
        try:
            tool_results["get_order_status"] = json.loads(raw)
        except Exception:
            tool_results["get_order_status"] = {"raw": raw}

    # 2) 查退货政策（仅当有品类，或订单返回的品类可用，或 intent==refund）
    if "check_refund_policy" not in tool_results:
        cat = category
        if not cat and order_id:
            order_info = tool_results.get("get_order_status") or {}
            cat = order_info.get("category")
        if cat:
            raw = check_refund_policy.invoke({"category": cat})
            try:
                tool_results["check_refund_policy"] = json.loads(raw)
            except Exception:
                tool_results["check_refund_policy"] = {"raw": raw}

    return {"tool_results": tool_results}


# ----------------------------------------------------------------------
# 综合回复节点：基于工具结果生成最终回答
# ----------------------------------------------------------------------

_GENERATE_PROMPT = """你是电商售后 AI 助手。请基于「工具返回结果」和用户诉求，撰写一份友好、清晰的最终答复。

要求：
1. 直接回答用户的核心问题（订单状态、退货政策是否符合、是否可退货）
2. 引用具体工具返回中的关键事实（订单号、状态、政策条款）
3. 给出可执行的建议（如何退货、需要哪些步骤、预计处理时长等）
4. 末尾简短致歉或安抚（保持专业）
"""


def generate_node(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """基于工具结果生成综合答复。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.llm import get_llm

    tool_results = state.get("tool_results") or {}
    intent = state.get("intent", "")
    product = state.get("product")
    order_id = state.get("order_id")
    reason = state.get("reason")

    context_parts = [
        f"用户意图: {intent}",
        f"提取商品: {product}",
        f"提取订单号: {order_id}",
        f"用户诉求: {reason}",
        "",
        "工具返回结果:",
        json.dumps(tool_results, ensure_ascii=False, indent=2),
    ]
    context = "\n".join(context_parts)

    llm = get_llm(temperature=0.3)
    messages = [
        SystemMessage(content=_GENERATE_PROMPT),
        HumanMessage(content=context),
    ]

    # 流式输出
    on_token = (config or {}).get("configurable", {}).get("stream_callback")
    if on_token:
        chunks = []
        for chunk in llm.stream(messages):
            text = chunk.content or ""
            chunks.append(text)
            on_token(text)
        final = "".join(chunks).strip()
    else:
        resp = llm.invoke(messages)
        final = (resp.content or "").strip()

    return {
        "final_response": final,
        "messages": [AIMessage(content=final)],
    }


# ----------------------------------------------------------------------
# 转人工节点
# ----------------------------------------------------------------------

def escalate_node(state: AgentState) -> AgentState:
    """情绪风控：直接转人工。"""
    reason = state.get("reason") or "用户情绪激动，已触发情绪风控转人工"
    raw = escalate_to_human.invoke({"reason": reason})
    try:
        result = json.loads(raw)
    except Exception:
        result = {"raw": raw}

    final = (
        f"非常抱歉给您带来不愉快的体验，我已为您转接人工客服。\n"
        f"客服坐席：{result.get('agent', '人工客服')}\n"
        f"排队位置：第 {result.get('queue_position', 1)} 位\n"
        f"转接原因：{reason}"
    )

    return {
        "final_response": final,
        "tool_results": {"escalate_to_human": result},
        "messages": [AIMessage(content=final)],
    }


# ----------------------------------------------------------------------
# 追问节点：反问用户
# ----------------------------------------------------------------------

def ask_info_node(state: AgentState) -> AgentState:
    """反问节点：当缺少订单号时，让用户补充。"""
    question = state.get("info_question") or "请提供您的订单号。"
    return {
        "final_response": question,
        "messages": [AIMessage(content=question)],
    }


# ----------------------------------------------------------------------
# 直接回复节点（闲聊/兜底）
# ----------------------------------------------------------------------

def direct_node(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """兜底回复：交给 LLM 自由回答。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.llm import get_llm

    last_user = ""
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "type", None) == "human":
            last_user = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    llm = get_llm(temperature=0.5)
    messages = [
        SystemMessage(
            content="你是电商售后 AI 助手。请用中文友好地回应用户，若无法解答请引导联系人工客服。"
        ),
        HumanMessage(content=last_user),
    ]

    # 流式输出
    on_token = (config or {}).get("configurable", {}).get("stream_callback")
    if on_token:
        chunks = []
        for chunk in llm.stream(messages):
            text = chunk.content or ""
            chunks.append(text)
            on_token(text)
        final = "".join(chunks).strip()
    else:
        resp = llm.invoke(messages)
        final = (resp.content or "").strip()

    return {
        "final_response": final,
        "messages": [AIMessage(content=final)],
    }


# ----------------------------------------------------------------------
# 路由函数：analyze 之后去哪？
# ----------------------------------------------------------------------

def route_after_analyze(state: AgentState) -> str:
    route = state.get("route") or "direct"
    if route == "escalate":
        return "escalate"
    if route == "ask_info":
        return "ask_info"
    if route == "tools":
        return "tools"
    return "direct"


# ----------------------------------------------------------------------
# 构建图
# ----------------------------------------------------------------------

def build_graph():
    """构建 LangGraph 工作流（带内存 checkpointer）。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("analyze", analyze_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("escalate", escalate_node)
    workflow.add_node("ask_info", ask_info_node)
    workflow.add_node("direct", direct_node)

    workflow.add_edge(START, "analyze")

    workflow.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {
            "escalate": "escalate",
            "ask_info": "ask_info",
            "tools": "tools",
            "direct": "direct",
        },
    )

    workflow.add_edge("tools", "generate")
    workflow.add_edge("escalate", END)
    workflow.add_edge("ask_info", END)
    workflow.add_edge("generate", END)
    workflow.add_edge("direct", END)

    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    return app


# 单例图（按需懒加载）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
