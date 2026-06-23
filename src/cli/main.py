"""电商售后中控系统 CLI。

启动命令：
    python -m src.cli
    python -m src.cli --verbose      # 显示状态摘要
"""

from __future__ import annotations

import os
os.environ.setdefault("LANGCHAIN_OPENAI_TCP_KEEPALIVE", "0")

import argparse
import json
import sys
import uuid

from langchain_core.messages import HumanMessage

from src.graph import get_graph

BANNER = r"""
+==============================================================+
|          智能电商售后中控系统 CLI Demo                        |
|          AgentRouter + LangGraph + DeepSeek                   |
+==============================================================+

  支持多轮对话，输入问题后自动识别意图、调用工具、生成回复。

  特殊命令:
    /state    显示当前状态摘要
    /reset    重置会话（开始新对话）
    /help     显示帮助
    /exit     退出
"""

HELP = """
命令:
  /state    显示当前会话的状态摘要（意图/情绪/订单号/品类/路由等）
  /reset    重置会话，开始一轮全新对话
  /help     显示此帮助信息
  /exit     退出 CLI

场景示例:
  "我的蓝牙耳机订单 ORD-2024 有杂音，想退货"
  "帮我查一下快递到哪了"
  "是 ORD-9999"              （补全上一轮追问的订单号）
  "你们这什么垃圾服务！我要投诉！"
"""

# 路由提示文案（无 emoji）
_ROUTE_HINTS = {
    "escalate": "[路由] 情绪风控 -> 转人工",
    "ask_info": "[路由] 缺失信息 -> 追问用户",
    "tools":    "[路由] 工具调用",
    "direct":   "[路由] 直接回复",
}


def _print_state(state: dict) -> None:
    summary = {
        "intent": state.get("intent"),
        "emotion": state.get("emotion"),
        "order_id": state.get("order_id"),
        "category": state.get("category"),
        "product": state.get("product"),
        "route": state.get("route"),
        "tool_results": list((state.get("tool_results") or {}).keys()),
    }
    print("\n+- 状态摘要 ---------------------------------")
    for k, v in summary.items():
        print(f"|  {k:<15}: {v}")
    print("+--------------------------------------------\n")


def _print_route_hint(state: dict) -> None:
    route = state.get("route")
    hint = _ROUTE_HINTS.get(route, f"[路由] {route}")
    print(f"   {hint}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="电商售后中控系统 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示状态摘要（意图/情绪/工具调用等）",
    )
    args = parser.parse_args()

    print(BANNER)

    graph = get_graph()
    thread_id = f"cli-{uuid.uuid4().hex[:6]}"
    print(f"会话 ID: {thread_id}")
    print("输入问题开始对话，输入 /exit 退出，输入 /help 查看帮助\n")

    turn = 0
    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n再见！")
            return

        if not user_input:
            continue

        # 命令处理
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ("/exit", "/quit", "/q"):
                print("\n再见！")
                return
            elif cmd == "/reset":
                thread_id = f"cli-{uuid.uuid4().hex[:6]}"
                turn = 0
                print(f"\n[v] 会话已重置，新会话 ID: {thread_id}\n")
                continue
            elif cmd == "/help":
                print(HELP)
                continue
            elif cmd == "/state":
                if turn > 0:
                    print("\n提示: /state 在回复后显示，请先输入问题\n")
                else:
                    print("\n提示: 还没有对话记录，请先输入问题\n")
                continue
            else:
                print(f"未知命令: {user_input}，输入 /help 查看帮助\n")
                continue

        turn += 1
        print(f"\n   [第 {turn} 轮] 处理中...")

        try:
            # 流式输出: 逐 token 打印并缓存
            stream_buffer = []

            def _stream_token(token: str) -> None:
                stream_buffer.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()

            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "stream_callback": _stream_token,
                }
            }
            state_in = {"messages": [HumanMessage(content=user_input)]}

            print("\n[客服] ", end="", flush=True)
            state = graph.invoke(state_in, config=config)

            final_text = (state.get("final_response") or "").strip()
            streamed_text = "".join(stream_buffer).strip()

            if stream_buffer and streamed_text:
                # 流式节点已输出内容，只需换行
                sys.stdout.write("\n")
                sys.stdout.flush()
            else:
                # 非流式节点（ask_info/escalate），打印 final_response
                sys.stdout.write(final_text)
                sys.stdout.write("\n")
                sys.stdout.flush()

            # 打印路由提示
            _print_route_hint(state)

            # verbose 模式显示状态摘要
            if args.verbose:
                _print_state(state)

            print()

        except KeyboardInterrupt:
            print("\n   已中断当前处理")
            continue
        except Exception as e:
            print(f"\n   [错误] {e}\n")
            continue


if __name__ == "__main__":
    main()
