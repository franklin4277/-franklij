# 如何扩展 Mini-Agent

三种方式：Tool / MCP / Skill

## 一、加 Tool（原子动作）

**适合**：一个函数调用、一次 HTTP 请求、一个文件操作。

### 做法

在 `mini_agent/tools/` 下写一个 Python 类：

```python
from mini_agent.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self):
        return "my_tool"

    @property
    def description(self):
        return "用 1 句话描述这个工具做什么"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "参数说明",
                },
            },
            "required": ["input"],
        }

    async def execute(self, *, input: str, **kwargs) -> ToolResult:
        # 你的逻辑
        return ToolResult(success=True, content=f"结果: {input}")
```

### 注册

```python
plugins = Plugins()
plugins.register_tool(MyTool())
```

**或**：放到 `mini_agent/tools/` 目录，Plugins 启动时自动发现。

### 示例

- `ReadTool`: 读文件
- `BashTool`: 执行命令
- `SessionNoteTool`: 记录笔记

## 二、加 MCP（外部服务）

**适合**：连接第三方 MCP server（SQLBot、GitHub、Filesystem 等）。

### 做法

编辑 `mcp.json`（放在项目根或 `mini_agent/config/` 下）：

```json
{
  "mcpServers": {
    "sqlbot": {
      "type": "streamable_http",
      "url": "http://localhost:8001/mcp"
    },
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

### 配置查找顺序

首个存在的优先：
1. 命令行 `--mcp-config <path>`
2. `./mcp.json`（项目根）
3. `~/.mini-agent/config/mcp.json`（用户全局）
4. `mini_agent/config/mcp.json`（包内默认）
5. `mini_agent/config/mcp-example.json`（模板）

### 启动时加载

```python
plugins = Plugins()
await plugins.load_mcp_servers()
# SQLBot 的所有工具（access_token、mcp_question 等）已暴露给 LLM
```

## 三、加 Skill（能力组合）

**适合**：复杂能力（封装多步流程，需要 SKILL.md 指令文档）。

### 做法

创建文件夹，至少含 `SKILL.md`：

```
skills/my_skill/
├── SKILL.md           # 必须：YAML frontmatter + Markdown
├── scripts/           # 可选：Python 脚本
│   └── run.py
├── references/        # 可选：文档
│   └── api.md
└── assets/            # 可选：模板
    └── template.html
```

#### `SKILL.md` 格式

```markdown
---
name: my_skill
description: 一句话描述
when_to_use: 何时使用此 Skill
inputs:
  - question: string (required) - 说明
outputs: 输出说明
---

# my_skill

## 工作流
1. 步骤 1
2. 步骤 2
...
```

#### `scripts/run.py`

LLM 调 `run_skill("my_skill", input="...")` 后，框架返回 SKILL.md 指令。
如果 script 本身包含可执行的 `ask()` 函数，LLM 可参考其模式。

### 示例：data_query Skill

详见 `skills/data_query/SKILL.md` + `scripts/ask.py`。

## 四、三种方式对比

| 维度 | Tool | MCP | Skill |
|------|------|-----|-------|
| 形态 | Python 类 | JSON 配置 | 文件夹 |
| 添加方式 | 写 .py | 编辑 mcp.json | 建文件夹 |
| 粒度 | 原子 | 多个工具 | 一组工具 + 文档 |
| 发现方式 | 自动 / 手动 | 配置驱动 | 文件系统扫描 |
| 复杂度 | 中（需懂 Python）| 低（配 URL）| 低（写 Markdown）|
| 标配示例 | ReadFile, BashTool | SQLBot | data_query |

## 五、配置开关

`config.yaml`：

```yaml
tools:
  enable_file_tools: true
  enable_bash: true
  enable_note: true
  enable_mcp: true         # ⭐ 是否加载 MCP
  enable_skills: true      # ⭐ 是否发现 Skills
  mcp_config_path: "mcp.json"
  skills_dirs:             # ⭐ Skills 目录（多路径）
    - "./skills"
    - "mini_agent/skills"
```

## 六、最终启动流程

```python
# mini_agent/cli.py（v3.4+）
from mini_agent.core.plugins import Plugins

plugins = Plugins(
    skills_dirs=config.tools.skills_dirs,
    workspace_dir=workspace_dir,
)

# 1. 注册内置 Tool
plugins.discover_tools("mini_agent/tools")

# 2. 加载 MCP server（异步）
if config.tools.enable_mcp:
    await plugins.load_mcp_servers()

# 3. 发现 Skills
if config.tools.enable_skills:
    plugins.discover_skills()

# 4. 创建 Agent
agent = Agent(
    llm_client=llm,
    system_prompt=system_prompt,
    plugins=plugins,
)

print(plugins.stats())
# {'tools': 5, 'mcp_tools': 6, 'skills': 1, 'total': 15}
```