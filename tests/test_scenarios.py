"""端到端验证：3 个核心场景的回归测试。

运行：pytest tests/test_scenarios.py -v
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import HumanMessage

from src.graph import get_graph


@pytest.fixture(scope="module")
def graph():
    return get_graph()


def _run(graph, thread_id: str, user_text: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke({"messages": [HumanMessage(content=user_text)]}, config=config)


# ------------------- 场景 A -------------------

def test_scenario_a_multistep_refund(graph):
    """场景A：蓝牙耳机退货 - 多步逻辑 + 工具编排 + 综合答复。"""
    tid = f"test-A-{uuid.uuid4().hex[:6]}"
    state = _run(
        graph,
        tid,
        "我上周买的那个蓝牙耳机，订单号：ORD-2024，现在有杂音，我想退货，看看符合政策吗？",
    )

    # 1. 实体识别：蓝牙耳机 → 电子产品
    assert state.get("category") == "电子产品", f"category 提取失败: {state.get('category')}"

    # 2. 流程编排：调用了 get_order_status 与 check_refund_policy
    tool_results = state.get("tool_results") or {}
    assert "get_order_status" in tool_results, "未调用 get_order_status"
    assert "check_refund_policy" in tool_results, "未调用 check_refund_policy"
    assert tool_results["get_order_status"].get("ok") is True
    assert tool_results["check_refund_policy"].get("ok") is True

    # 3. 最终输出存在且非空
    final = state.get("final_response") or ""
    assert final, "未生成最终答复"
    assert len(final) > 20, f"最终答复过短: {final!r}"

    # 答复中应至少提到「退货」与订单状态关键信息
    assert any(k in final for k in ("退货", "7天", "退款"))


# ------------------- 场景 B -------------------

def test_scenario_b_missing_info_followup(graph):
    """场景B：先反问，补充订单号后完成查询。"""
    tid = f"test-B-{uuid.uuid4().hex[:6]}"

    # 第 1 轮：缺少 order_id → 反问
    state1 = _run(graph, tid, "帮我查一下我的快递到哪了？")
    assert state1.get("needs_info") is True, f"第1轮应识别为需要追问: {state1}"
    assert state1.get("route") == "ask_info", f"路由错误: {state1.get('route')}"
    assert "订单号" in (state1.get("final_response") or "")

    # 第 2 轮：补充 order_id → 接上上下文完成查询
    state2 = _run(graph, tid, "是 ORD-9999")
    assert state2.get("order_id") == "ORD-9999", f"订单号未正确提取: {state2.get('order_id')}"

    # 不再追问
    assert state2.get("route") in ("tools", "direct"), f"第2轮路由错误: {state2.get('route')}"
    final2 = state2.get("final_response") or ""
    assert final2 and len(final2) > 5

    # 应调用了工具并返回订单信息
    tool_results = state2.get("tool_results") or {}
    if tool_results:
        # 如果走了 tools 路由，至少有订单状态
        if "get_order_status" in tool_results:
            assert tool_results["get_order_status"].get("ok") is True


# ------------------- 场景 C -------------------

def test_scenario_c_emotion_escalate(graph):
    """场景C：识别愤怒情绪 → 直接转人工，跳过常规 AI 流程。"""
    tid = f"test-C-{uuid.uuid4().hex[:6]}"
    state = _run(graph, tid, "你们这是什么垃圾服务！我都等了十天了！我要投诉！")

    # 情绪识别为 angry
    assert state.get("emotion") == "angry", f"情绪未识别: {state.get('emotion')}"

    # 路由到 escalate
    assert state.get("route") == "escalate", f"路由错误: {state.get('route')}"

    # 调用了 escalate_to_human
    tool_results = state.get("tool_results") or {}
    assert "escalate_to_human" in tool_results, "未调用 escalate_to_human"
    assert tool_results["escalate_to_human"].get("transferred") is True

    # 最终答复包含转人工信息
    final = state.get("final_response") or ""
    assert "人工" in final, f"最终答复未提及人工客服: {final}"
