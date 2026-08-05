---
name: data_query
description: 用自然语言查询 SQLBot 数据库，返回 Markdown 表格 + 图表路径
when_to_use: |
  用户问"销售/客流/订单"等业务数据问题；或要求查询具体指标、统计、趋势分析。
  不适合：web 搜索、文件读写、命令执行。
inputs:
  - question: string (required) - 自然语言问题
  - datasource_id: integer (optional) - 数据源 ID，未指定则用第一个可用
mcp_server: sqlbot
outputs: |
  返回 Markdown 格式的查询结果，包含：
  - 标题（LLM 生成的总结）
  - 表格（数据）
  - 图表路径（如有）
  - 原始 SQL（透明性）
---

# data_query Skill

## 工作流

调用 `scripts/ask.py` 的 `ask()` 函数，自动完成以下步骤：

1. **连接 SQLBot MCP server**（`mcp.json` 配置）
2. **登录**：`access_token` 工具
3. **创建会话**：`mcp_start` 工具
4. **执行查询**：`mcp_question` 工具
5. **渲染 Markdown** 表格

## 工具映射

| SQLBot MCP 工具 | 用途 | 封装在 ask() |
|----------------|------|-------------|
| `access_token` | 登录拿 JWT | 步骤 2 |
| `mcp_start` | 创建会话拿 chat_id | 步骤 3 |
| `mcp_question` | 发起查询 | 步骤 4 |
| `mcp_datasource_list` | 列数据源 | 备选 |
| `mcp_ws_list` | 列工作空间 | 备选 |

## 错误处理

- SQLBot 不可达 → 返回 "SQLBot 服务暂不可用"
- Token 失效 → 自动重新登录
- 问题模糊 → 让 LLM 调用 `mcp_datasource_list` 让用户选数据源
- 数据源无效 → 返回 "请指定有效的数据源 ID"

## 性能

- 单次查询：3-5 秒
- 上下文用完后支持多轮（同 session 自动延续）

## 示例

```python
# 在 scripts/ask.py 中
result = await ask(
    question="上海虹桥各品牌总销售额",
    datasource_id=9
)
# 返回: {"answer_md": "...", "sql": "...", "chart_path": "..."}
```
