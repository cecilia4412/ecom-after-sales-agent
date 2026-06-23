# Agent 工作流

## 1. 整体流程

```mermaid
graph TB
    START([START: 用户输入]) --> analyze

    analyze[analyze_node<br/>DeepSeek LLM 调用<br/>情绪检测 + 意图分类 + 实体抽取<br/>输出: emotion / intent / order_id / category / product]

    analyze --> route_check{route_after_analyze<br/>条件路由}

    route_check -->|emotion=angry<br/>或 intent=complaint| escalate
    route_check -->|缺少 order_id| ask_info
    route_check -->|intent=query_order<br/>refund/policy| tools
    route_check -->|chitchat/other| direct

    escalate[escalate_node<br/>调用 escalate_to_human 工具<br/>返回坐席号 + 排队位 + 转接原因]
    escalate --> END_ESCALATE([END: 已转人工客服])

    ask_info[ask_info_node<br/>生成反问文本<br/>请提供您的订单号]
    ask_info --> END_ASK([END: 等待用户补充])
    END_ASK -. "用户补充输入<br/>同一 thread_id" .-> START

    tools[tool_node<br/>get_order_status 查订单状态<br/>check_refund_policy 查退货政策]
    tools --> generate

    generate[generate_node<br/>DeepSeek LLM 调用<br/>综合工具结果生成最终答复<br/>支持流式输出]
    generate --> END_GEN([END: 综合答复])

    direct[direct_node<br/>DeepSeek LLM 调用<br/>兜底自由回复<br/>支持流式输出]
    direct --> END_DIR([END: 直接回复])
```

## 2. 节点流转关系

| 节点 | 触发条件 | 调用的工具/LLM | 输出到 State | 下一节点 |
| --- | --- | --- | --- | --- |
| `analyze` | 每轮用户输入必经 | DeepSeek Chat (JSON 输出) | emotion, intent, order_id, category, product, route | `route_check` |
| `route_check` | analyze 之后 | 纯逻辑判断 (无 LLM) | -- | 四分支之一 |
| `escalate` | emotion=angry 或 intent=complaint | escalate_to_human (Mock) | tool_results, final_response | END |
| `ask_info` | intent=query_order/refund 且缺少 order_id | 无 (模板文本) | final_response, info_question | END (等待下一轮) |
| `tools` | intent=query_order/refund/policy 且有 order_id | get_order_status + check_refund_policy (Mock) | tool_results | `generate` |
| `generate` | tools 执行完毕 | DeepSeek Chat (流式) | final_response | END |
| `direct` | 闲聊/兜底场景 | DeepSeek Chat (流式) | final_response | END |

## 3. 三个场景的流转路径

### 场景 A: 多步逻辑 (蓝牙耳机退货)

```mermaid
graph LR
    A([用户: 蓝牙耳机 ORD-2024 有杂音想退货]) --> B[analyze]
    B --> C{route_check}
    C -->|intent=refund, 有order_id| D[tools]
    D --> E[generate]
    E --> F([综合答复: 订单已发货 + 电子产品7天可退])
```

**关键数据流:**
- analyze 输出: `intent=refund`, `emotion=calm`, `order_id=ORD-2024`, `category=电子产品`
- tools 调用: `get_order_status(ORD-2024)` -> 已发货 + `check_refund_policy(电子产品)` -> 7天可退
- generate: 综合两个工具结果，生成包含订单状态 + 退货建议的答复

### 场景 B: 缺失信息追问 (查快递)

```mermaid
graph LR
    A([用户: 帮我查一下快递到哪了]) --> B[analyze]
    B --> C{route_check}
    C -->|intent=query_order, 无order_id| D[ask_info]
    D --> E([反问: 请提供订单号])
    E -->|用户补充: ORD-9999| F[analyze]
    F --> G{route_check}
    G -->|intent=query_order, 有order_id| H[tools]
    H --> I[generate]
    I --> J([综合答复: 订单运输中])
```

**关键数据流:**
- 第 1 轮: analyze 识别 `intent=query_order` 但 `order_id=null` -> ask_info 反问
- 第 2 轮: MemorySaver 保留上下文，analyze 从补充输入提取 `order_id=ORD-9999` -> tools -> generate

### 场景 C: 情绪风控 (愤怒投诉)

```mermaid
graph LR
    A([用户: 什么垃圾服务! 等了十天! 我要投诉!]) --> B[analyze]
    B --> C{route_check}
    C -->|emotion=angry| D[escalate]
    D --> E([转人工: 坐席A2026, 排队第1位])
```

**关键数据流:**
- analyze 输出: `emotion=angry`, `intent=complaint`
- 路由判断: 情绪风控优先，跳过常规工具调用流程
- escalate 调用 `escalate_to_human("用户情绪激动")` -> 返回坐席号和排队位

## 4. State 字段在各节点的读写

```
                 analyze    escalate   ask_info    tools    generate   direct
messages         R          -          -           -        -          R
intent           W          R          R           R        R          -
emotion          W          R          -           -        -          -
order_id         W          -          R           R        -          -
category         W          -          -           R        -          -
product          W          -          -           -        R          -
reason           W          R          -           -        R          -
route            W          -          -           -        -          -
needs_info       W          -          W           -        -          -
info_question    -          -          W           -        -          -
tool_results     -          W          -           W        R          -
final_response   -          W          W           -        W          W
```

- `R` = 读取, `W` = 写入, `-` = 不涉及
