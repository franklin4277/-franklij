# Mini-Agent 平台架构文档

> **本项目的实际架构**（已实施）。
> 描述三个核心扩展点：Tool / MCP / Skill，以及它们如何通过 `Plugins` 统一管理。

## 一、产品定位

**Mini-Agent = 可扩展的 LLM Agent 平台**

### 核心能力

| 能力 | 形态 | 状态 |
|------|------|------|
| 问数 (data_query) | Skill（Anthropic 风格）| ✅ 已实现 |
| 文件操作 / Bash | Tool | ✅ 已实现 |
| MCP 服务器（SQLBot 等）| MCP 客户端 | ✅ 已实现 |
| （未来）网络搜索 | Skill | 待实现 |
| （未来）数据分析报告 | Sub-agent | 待实现 |

## 二、三个核心扩展点

| 扩展点 | 形态 | 添加方式 | 例子 |
|--------|------|---------|------|
| **Tool** | Python 类 | 写 `.py` 文件 | ReadTool、BashTool、NoteTool |
| **MCP** | 外部 server（stdio/HTTP/SSE）| 编辑 `mcp.json` | SQLBot、GitHub、Filesystem |
| **Skill** | 文件夹 + `SKILL.md` | 建文件夹 | data_query、web_search |

三者最终**都表现为 `Tool`**给 LLM 调用，由 **`Plugins`** 统一管理。

## 三、`Plugins`（统一注册表）

### 3.1 类签名

```python
class Plugins:
    """Unified registry: Tools + MCP + Skills."""
    
    def __init__(
        self,
        skills_dirs: list[str | Path] | None = None,  # Skills 多路径搜索
        workspace_dir: str | Path = "./workspace",
    ):
        ...
    
    # ---- Tools ----
    def register_tool(self, tool: Tool) -> None: ...
    def register_tools(self, tools: list[Tool]) -> None: ...
    def discover_tools(self, tools_dir: str | Path) -> int: ...
    
    # ---- MCP ----
    async def load_mcp_servers(self, config_path: str = "mcp.json") -> None: ...
    async def cleanup_mcp(self) -> None: ...
    
    # ---- Skills ----
    def discover_skills(self) -> int: ...
    def get_skill(self, name: str) -> Skill | None: ...
    def skill_names(self) -> list[str]: ...
    
    # ---- Aggregation ----
    def all_tools(self) -> list[Tool]: ...              # 全部 Tool
    def system_prompt_addition(self) -> str: ...      # Skills 描述
    def stats(self) -> dict[str, int]: ...
```

### 3.2 三种来源的 Tool

```python
all_tools() 返回：
├── [1] user.register_tool() 加入的 Tool
├── [2] mcp.load_mcp_servers() 加载的 MCP Tool（来自 mcp.json）
└── [3] 如果有 skills，添加一个共享的 run_skill(skill_name, input) Tool
```

### 3.3 启动流程

```python
# mini_agent/cli.py
plugins = Plugins(skills_dirs=["./skills", "mini_agent/skills"])
plugins.discover_tools("mini_agent/tools")  # Tool 自动扫描
await plugins.load_mcp_servers()           # 加载 MCP
plugins.discover_skills()                  # 发现 Skills

agent = Agent(llm_client=llm, system_prompt=..., plugins=plugins)
```

### 3.4 Skills 多路径搜索

`discover_skills()` 扫描所有 `skills_dirs`，**先到先得**（后面路径不覆盖前面的）。默认路径：

| 优先级 | 路径 | 用途 |
|--------|------|------|
| 1 | `./skills/` | 用户项目级 skills |
| 2 | `mini_agent/skills/` | 包内置 skills（如 Anthropic 的 15 个）|
| 3 | `~/.mini-agent/skills/` | 用户全局 skills |

## 四、Tool（原子动作）

```python
from mini_agent.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self): return "my_tool"
    @property
    def description(self): return "一句话描述"
    @property
    def parameters(self): return {"type": "object", "properties": {...}}
    
    # 可选：框架会注入资源（workspace_dir、llm 等）
    def bind_resources(self, **resources) -> None: ...
    
    async def execute(self, **kwargs) -> ToolResult: ...
```

**添加方式**：
- 写类 → 放 `mini_agent/tools/` → 自动发现
- 或 `plugins.register_tool(MyTool())` 手动注册

## 五、MCP（外部服务器）

编辑 `mcp.json`：

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

**查找顺序**：
1. 命令行 `--mcp-config <path>`
2. `./mcp.json`（项目根）
3. `~/.mini-agent/config/mcp.json`（用户全局）
4. `mini_agent/config/mcp.json`（包内默认）
5. `mcp-example.json`（模板）

## 六、Skill（Anthropic 风格文件夹）

### 6.1 标准结构

```
skills/<skill_name>/
├── SKILL.md            # 必须：YAML frontmatter + Markdown
├── scripts/            # 可选：Python 脚本
├── references/         # 可选：参考文档
└── assets/             # 可选：模板
```

### 6.2 SKILL.md 格式

```markdown
---
name: my_skill
description: 一句话描述（LLM 看到这句决定是否调用）
when_to_use: 何时使用
inputs:
  - question: string (required)
outputs: 输出说明
---

# my_skill

## 工作流
1. 步骤 1
2. 步骤 2
```

### 6.3 LLM 调用方式

`run_skill(skill_name="my_skill", input="用户输入")` → 返回 SKILL.md 全文 → LLM 按指令执行后续步骤。

### 6.4 示例：data_query Skill

```yaml
# skills/data_query/SKILL.md
---
name: data_query
description: 用自然语言查询 SQLBot 数据库
when_to_use: 用户问"销售/客流/订单"等数据问题
---

# data_query Skill
## 工作流
1. login
2. create session
3. run query
4. render Markdown
```

```python
# skills/data_query/scripts/ask.py（高层封装）
async def ask(question, datasource_id=None):
    """隐藏 token/chat_id 细节，LLM 只看到一个干净接口。"""
    with SqlBotClient(cfg) as client:
        token = client.login()
        token, chat_id = client.start_session(token)
        raw = client.ask(token=token, chat_id=chat_id, question=question, ...)
        return render(raw)
```

## 七、Agent（消费者）

```python
class Agent:
    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool] | None = None,          # 旧 API（保留）
        plugins: Plugins | None = None,            # ⭐ 新 API
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
    ):
        # 工具来源：plugins + 显式 tools（两者可共存）
        ...
        self.tools = {t.name: t for t in all_tools}
```

**向后兼容**：
- 旧 `Agent(tools=[...])` 继续工作
- 新 `Agent(plugins=plugins)` 推荐shayuhao

## 八、实际目录结构

```
mini-agent/
├── web/                        # Next.js UI（顶层）
├── mini_agent/                 # Python 包
│   ├── __init__.py
│   ├── cli.py                  # 主 CLI
│   ├── agent.py                # Agent 类（支持 plugins=）
│   ├── config.py
│   ├── schema.py / schema/     # 数据模型（LLMResponse、Message 等）
│   ├── logger.py               # 日志与重试
│   ├── render.py               # Markdown 渲染
│   ├── terminal.py             # 终端显示工具
│   ├── llm/                    # LLM 客户端层
│   │   ├── base.py             # 抽象基类
│   │   ├── anthropic_client.py # Anthropic 协议
│   │   ├── openai_client.py    # OpenAI 协议
│   │   └── llm_wrapper.py      # 统一 LLMClient
│   ├── tools/                  # ⭐ Tool 库
│   │   ├── base.py / bash_tool.py / ...  # 向后兼容 shim
│   │   ├── builtin/            # 内置工具实现
│   │   │   ├── base.py         # Tool 基类 + ToolResult
│   │   │   ├── bash_tool.py    # Shell 命令执行
│   │   │   ├── file_tools.py   # 文件读写编辑
│   │   │   └── note_tool.py    # 会话笔记
│   │   └── loaders/            # 外部工具加载器
│   │       └── mcp_loader.py   # MCP 协议客户端
│   ├── core/                   # ⭐ 核心抽象
│   │   ├── plugins.py          # Plugins 统一注册表
│   │   ├── skill.py            # Skill + SkillManager
│   │   ├── orchestrator.py     # ReAct 编排器
│   │   ├── events.py           # 流式事件类型
│   ├── connectors/             # 外部服务连接器
│   │   └── sqlbot.py           # SQLBot HTTP 客户端
│   ├── memory/                 # 会话持久化
│   │   └── session.py          # SessionStore
│   ├── api/                    # FastAPI 服务器
│   ├── acp/                    # ACP 集成（Zed 编辑器）
│
├── skills/                     # ⭐ 用户项目级 Skills
│   └── data_query/             # 当前唯一一个自定义 Skill
│       ├── SKILL.md
│       └── scripts/ask.py
│
├── mini_agent/skills/          # ⭐ 包内置 Skills（Anthropic 子模块）
│   ├── algorithmic-art/
│   ├── artifacts-builder/
│   └── ... (15 个)
│
├── mcp.json                    # ⭐ MCP server 配置（项目级）
├── docs/
│   ├── EXTENDING.md            # 如何扩展
│   ├── MCP_INTEGRATION.md      # MCP 接入指南
│   ├── AGENT_FLOWS.md          # 流程时序图
│   ├── DATA_AGENT_DESIGN.md    # data_query 早期设计
│   └── AGENT_PLATFORM_V3.md    # 旧设计（v3，已被 v3.1 取代）
└── tests/
```

## 九、添加新功能的 3 个步骤

### 加 Tool
1. 在 `mini_agent/tools/` 写一个 `.py` 类
2. 重新启动，Plugins 自动发现

### 加 MCP
1. 编辑 `mcp.json`（项目根或包内）
2. 重新启动，Plugins 自动加载

### 加 Skill
1. `mkdir -p skills/my_skill`
2. 创建 `skills/my_skill/SKILL.md`
3. 重新启动，Plugins 自动发现

## 十、ADR 记录

| ADR | 标题 | 状态 |
|-----|------|------|
| 025-029 | mini_agent 结构整理 | ✅ |
| 030-031 | core/ 不引入 / plugins 命名 | ✅ |
| 032 | 旧路径 shim 兼容 | ✅ |
| **033** | **`Plugins` 统一注册表**（Tool + MCP + Skill）| ✅ 已实施 |
| **034** | **Skill = 文件夹**（Anthropic 标准）| ✅ 已实施 |
| **035** | **MCP 优先用配置文件**（mcp.json）| ✅ 已实施 |
| 036 | LLM 角色收敛（可选 clarify/summarize）| 提议 |
| 037 | data_query 重写为 Skill | ✅ 已实施 |

## 十一、关键决策（最终）

| 决策 | 推荐 | 实施状态 |
|------|------|----------|
| 顶层分组：核心入 `core/` | ❌ 保持扁平 | ✅ |
| Skill = 文件夹（Anthropic 标准）| ✅ | ✅ |
| MCP = 配置驱动 | ✅ | ✅ |
| Tool = Python 类 | ✅ | ✅ |
| **`Plugins` 统一管理** | ✅ | ✅ |
| `run_skill` 共享工具（每 Skill 不单独 Tool）| ✅ | ✅ |
| Skills 多路径搜索（用户 > 包内 > 全局）| ✅ | ✅ |
| MCP 配置多路径 fallback | ✅ | ✅ |
| Agent 向后兼容（tools 列表 + plugins）| ✅ | ✅ |

## 十二、相关文档

- `EXTENDING.md` — 如何添加 Tool / MCP / Skill
- `AGENT_FLOWS.md` — 流程时序图（含问数流程）