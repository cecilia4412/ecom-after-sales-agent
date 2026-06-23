# 交付清单

## 一、核心实现文件

| 文件 | 作用 |
| --- | --- |
| `src/state.py` | **State 定义**：`AgentState` TypedDict |
| `src/router.py` | **Router 逻辑**：`analyze_node` 意图分析 + 情绪检测 + 实体抽取 |
| `src/graph.py` | **LangGraph 工作流**：analyze → {escalate / ask_info / tools→generate / direct} |
| `src/tools.py` | 3 个 Mock 工具：`get_order_status` / `check_refund_policy` / `escalate_to_human` |
| `src/llm.py` | DeepSeek Chat 接入（OpenAI 兼容协议） |
| `src/__main__.py` | Demo 入口（三个场景端到端运行） |
| `src/cli/main.py` | CLI 交互入口（多轮对话、流式输出） |
| `tests/test_scenarios.py` | pytest 端到端测试 |

```bash
# 运行场景
python -m src --scenario all

# 运行测试
python -m pytest tests/test_scenarios.py -v

# CLI 交互
python -m src.cli
```

## 二、架构流程图

参见 [docs/workflow.md](docs/workflow.md)，包含：
- 整体 Agent 工作流 Mermaid 图（6 个节点的流转关系）
- 节点职责与触发条件对照表
- 场景 A / B / C 各自的流转路径子图
- State 字段在各节点的读写矩阵

## 三、运行日志

| 文件 | 说明 |
| --- | --- |
| [output/run_log.png](output/run_log.png) | 运行截图（终端风格） |
| [output/run_log.txt](output/run_log.txt) | 纯文本运行日志 |
| [output/run_log.html](output/run_log.html) | 终端风格 HTML |

覆盖：
- 场景 A：实体识别 + 工具调用 + 综合答复
- 场景 B：追问 + 上下文补全 + 完整查询
- 场景 C：愤怒情绪识别 + 直接转人工

## 四、技术栈

- **LLM**：DeepSeek Chat（`deepseek-chat`），OpenAI 兼容协议
- **Agent 框架**：LangChain + LangGraph
- **运行时**：Python 3.13
