"""Gradio 对话页面 — 最简单的聊天界面。

启动：
    python -m src.webui
"""

import os
import uuid

os.environ.setdefault("LANGCHAIN_OPENAI_TCP_KEEPALIVE", "0")

import gradio as gr
from langchain_core.messages import HumanMessage

from src.graph import get_graph

_graph = None
_thread_id = ""


def _init():
    global _graph, _thread_id
    if _graph is None:
        _graph = get_graph()
        _thread_id = f"web-{uuid.uuid4().hex[:6]}"


def chat(message: str) -> str:
    """处理用户消息，返回客服回复。"""
    _init()
    config = {"configurable": {"thread_id": _thread_id}}
    state = _graph.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )

    route = state.get("route", "")
    reply = state.get("final_response", "")

    route_labels = {
        "escalate": "[转人工]",
        "ask_info": "[追问]",
        "tools": "[工具调用]",
        "direct": "[直接回复]",
    }
    tag = route_labels.get(route, "")
    return f"{reply}\n\n*{tag}*" if tag else reply


def main():
    _init()

    with gr.Blocks(title="智能电商售后中控系统") as demo:
        gr.Markdown("# 智能电商售后中控系统\nLangGraph + DeepSeek Chat")

        chatbot = gr.Chatbot(height=500, show_label=False)
        with gr.Row():
            msg = gr.Textbox(
                placeholder="输入问题，如：帮我查一下快递到哪了",
                show_label=False,
                scale=8,
                container=False,
            )
            submit_btn = gr.Button("发送", variant="primary", scale=1)
        clear_btn = gr.Button("清空对话")

        def respond(user_msg, history):
            if not user_msg.strip():
                return history, ""
            reply = chat(user_msg)
            history = history + [{"role": "user", "content": user_msg},
                                 {"role": "assistant", "content": reply}]
            return history, ""

        submit_btn.click(respond, [msg, chatbot], [chatbot, msg])
        msg.submit(respond, [msg, chatbot], [chatbot, msg])
        clear_btn.click(lambda: ([], ""), None, [chatbot, msg])

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
