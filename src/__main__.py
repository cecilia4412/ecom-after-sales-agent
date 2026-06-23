"""智能电商售后中控系统入口。

用法：
    python -m src                       # 启动交互式 REPL
    python -m src --scenario A|B|C      # 运行指定场景（自动 + 手动输入可选）
"""

from __future__ import annotations

import os
os.environ.setdefault("LANGCHAIN_OPENAI_TCP_KEEPALIVE", "0")

import argparse
import json
import uuid

from langchain_core.messages import HumanMessage

from src.graph import get_graph


BANNER = r"""
============================================================
  智能电商售后中控系统  (AgentRouter + LangGraph + DeepSeek)
  场景: A=多步逻辑   B=追问补全   C=情绪风控转人工
============================================================
"""


def _print_state_summary(state: dict) -> None:
    print("\n---- 状态摘要 ----")
    summary = {
        "intent": state.get("intent"),
        "emotion": state.get("emotion"),
        "order_id": state.get("order_id"),
        "category": state.get("category"),
        "product": state.get("product"),
        "route": state.get("route"),
        "needs_info": state.get("needs_info"),
        "tool_results_keys": list((state.get("tool_results") or {}).keys()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_turn(graph, thread_id: str, user_text: str) -> dict:
    """单轮对话：注入用户输入，运行图，返回最终状态。"""
    config = {"configurable": {"thread_id": thread_id}}
    state_in = {"messages": [HumanMessage(content=user_text)]}
    final = graph.invoke(state_in, config=config)
    return final


def scenario_a() -> None:
    """场景A：多步逻辑 - 退货咨询，需要实体识别 + 工具编排 + 综合答复。"""
    print("\n" + "=" * 60)
    print("场景 A：多步逻辑（蓝牙耳机退货）")
    print("=" * 60)

    graph = get_graph()
    thread_id = f"demo-A-{uuid.uuid4().hex[:6]}"

    user_msg = "我上周买的那个蓝牙耳机，订单号：ORD-2024，现在有杂音，我想退货，看看符合政策吗？"
    print(f"\n[用户]: {user_msg}")

    state = run_turn(graph, thread_id, user_msg)
    _print_state_summary(state)
    print(f"\n[客服]: {state.get('final_response')}\n")


def scenario_b() -> None:
    """场景B：缺失信息追问 - 上下文记忆 + 反问 + 补充后继续执行。"""
    print("\n" + "=" * 60)
    print("场景 B：缺失信息追问（两轮对话）")
    print("=" * 60)

    graph = get_graph()
    thread_id = f"demo-B-{uuid.uuid4().hex[:6]}"

    user_msg1 = "帮我查一下我的快递到哪了？"
    print(f"\n[用户-第1轮]: {user_msg1}")
    state1 = run_turn(graph, thread_id, user_msg1)
    _print_state_summary(state1)
    print(f"\n[客服-第1轮]: {state1.get('final_response')}\n")

    user_msg2 = "是 ORD-9999"
    print(f"[用户-第2轮]: {user_msg2}")
    state2 = run_turn(graph, thread_id, user_msg2)
    _print_state_summary(state2)
    print(f"\n[客服-第2轮]: {state2.get('final_response')}\n")


def scenario_c() -> None:
    """场景C：情绪风控 - 识别愤怒情绪 → 直接转人工。"""
    print("\n" + "=" * 60)
    print("场景 C：情绪风控转人工")
    print("=" * 60)

    graph = get_graph()
    thread_id = f"demo-C-{uuid.uuid4().hex[:6]}"

    user_msg = "你们这是什么垃圾服务！我都等了十天了！我要投诉！"
    print(f"\n[用户]: {user_msg}")

    state = run_turn(graph, thread_id, user_msg)
    _print_state_summary(state)
    print(f"\n[客服]: {state.get('final_response')}\n")


def interactive_loop() -> None:
    print(BANNER)
    graph = get_graph()
    thread_id = f"repl-{uuid.uuid4().hex[:6]}"
    print(f"会话 ID: {thread_id}\n输入 exit / quit 退出\n")

    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        if user.lower() in ("exit", "quit", "q"):
            print("bye.")
            return
        if not user:
            continue
        state = run_turn(graph, thread_id, user)
        print(f"\n[客服]: {state.get('final_response')}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="智能电商售后中控系统 Demo")
    parser.add_argument(
        "--scenario",
        choices=["A", "B", "C", "all"],
        help="运行指定场景：A / B / C / all",
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="启动交互式 REPL",
    )
    args = parser.parse_args()

    if args.repl:
        interactive_loop()
        return

    if args.scenario in (None, "all"):
        scenario_a()
        scenario_b()
        scenario_c()
        return

    if args.scenario == "A":
        scenario_a()
    elif args.scenario == "B":
        scenario_b()
    elif args.scenario == "C":
        scenario_c()


if __name__ == "__main__":
    main()
