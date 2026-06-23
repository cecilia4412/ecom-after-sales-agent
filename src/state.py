"""AgentRouter 状态定义。

State 设计原则：
- messages: LangGraph 推荐使用 add_messages reducer，自动追加消息历史
- intent/emotion/order_id/category/product: 由意图分析节点写入的结构化字段
- tool_results: 工具节点累积的调用结果
- needs_info / info_question: 追问相关字段
- final_response: 终结态最终答复
- route: 路由标记（escalate / ask_info / tools / direct）
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


RouteName = Literal["escalate", "ask_info", "tools", "direct"]
EmotionLabel = Literal["angry", "calm", "neutral"]


class AgentState(TypedDict, total=False):
    """AgentRouter 全局状态。"""

    # 对话历史（自动累积）
    messages: Annotated[list, add_messages]

    # 意图分析结果
    intent: str                       # e.g. "refund" / "query_order" / "complaint" / ...
    emotion: EmotionLabel             # angry / calm / neutral
    order_id: str | None              # 提取的订单号
    category: str | None              # 提取的品类
    product: str | None               # 提取的商品
    reason: str | None                # 转人工原因

    # 路由决策
    route: RouteName
    needs_info: bool                  # 是否缺少必要信息
    info_question: str                # 反问用户的内容

    # 工具调用累积结果
    tool_results: dict[str, Any]

    # 最终答复
    final_response: str
