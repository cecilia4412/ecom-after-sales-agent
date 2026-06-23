"""LLM 配置模块：对接 DeepSeek Chat。"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载 .env
load_dotenv()


def _build_http_client() -> httpx.Client:
    """构建 HTTP 客户端。开发环境可禁用 SSL 验证以避免本地证书链缺失问题。

    生产环境应确保系统根证书齐全，不要禁用 SSL 验证。
    """
    ssl_verify = os.getenv("LLM_SSL_VERIFY", "0") == "1"
    return httpx.Client(verify=ssl_verify, timeout=60.0)


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """构建 DeepSeek Chat 实例。DeepSeek 兼容 OpenAI Chat Completions 协议。"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    if not api_key:
        raise RuntimeError(
            "未检测到 DEEPSEEK_API_KEY，请检查 .env 或环境变量。"
        )

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        http_client=_build_http_client(),
    )
