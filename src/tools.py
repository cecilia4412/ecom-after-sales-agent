"""Mock 工具模块：模拟电商售后系统的三个核心工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool


# 模拟订单数据库
_MOCK_ORDERS: dict[str, dict[str, Any]] = {
    "ORD-2024": {
        "order_id": "ORD-2024",
        "product": "蓝牙耳机",
        "category": "电子产品",
        "status": "已发货",
        "shipped_at": "2026-06-15",
    },
    "ORD-9999": {
        "order_id": "ORD-9999",
        "product": "运动鞋",
        "category": "服装鞋帽",
        "status": "运输中",
        "shipped_at": "2026-06-20",
    },
    "ORD-1234": {
        "order_id": "ORD-1234",
        "product": "智能手表",
        "category": "电子产品",
        "status": "已完成",
        "shipped_at": "2026-06-10",
    },
}


# 模拟品类与退货政策映射
_REFUND_POLICIES: dict[str, str] = {
    "电子产品": "电子产品支持7天无理由退货，需保持包装与配件完整。",
    "服装鞋帽": "服装鞋帽支持15天无理由退货，需保持吊牌完好。",
    "美妆护肤": "美妆护肤类商品不支持拆封后退货，但可申请质量问题退货。",
    "食品饮料": "食品饮料类商品除质量问题外不支持退货。",
    "家居日用": "家居日用支持7天无理由退货。",
}


@tool
def get_order_status(order_id: str) -> str:
    """查询订单状态。输入订单号（形如 ORD-2024），返回订单的当前状态、品类等信息。"""
    order = _MOCK_ORDERS.get(order_id)
    if order is None:
        return json.dumps(
            {"ok": False, "order_id": order_id, "message": f"未找到订单 {order_id}"},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, **order}, ensure_ascii=False)


@tool
def check_refund_policy(category: str) -> str:
    """查询指定品类的退货政策。输入品类（如「电子产品」「服装鞋帽」），返回对应的退货政策文案。"""
    policy = _REFUND_POLICIES.get(category)
    if policy is None:
        return json.dumps(
            {"ok": False, "category": category, "message": f"未收录品类 {category} 的政策"},
            ensure_ascii=False,
        )
    return json.dumps({"ok": True, "category": category, "policy": policy}, ensure_ascii=False)


@tool
def escalate_to_human(reason: str) -> str:
    """转接人工客服。reason 为转人工的原因说明（用户愤怒、复杂投诉、无法自助解决等）。"""
    return json.dumps(
        {
            "ok": True,
            "transferred": True,
            "agent": "人工客服坐席 #A2026",
            "queue_position": 1,
            "reason": reason,
            "message": "已为您转接人工客服，请稍候。",
        },
        ensure_ascii=False,
    )


# 工具注册表
ALL_TOOLS = [get_order_status, check_refund_policy, escalate_to_human]
