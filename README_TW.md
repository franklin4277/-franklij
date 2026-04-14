# Mini Agent

English | [中文](./README_CN.md)

**Mini Agent** 是一個精簡但專業的演示專案，展示使用 MiniMax M2.5 模型構建代理的最佳實踐。它利用 Anthropic 相容的 API，完全支援交錯思考（interleaved thinking），以釋放 M2 強大的推理能力，處理冗長且複雜的任務。

此專案配備了為穩健且智慧的代理開發體驗而設計的功能：

*   ✅ **完整代理執行循環**：一個完整且可靠的基礎，配備用於檔案系統和 shell 操作的基本工具集。
*   ✅ **持久記憶**：一個主動的**對話筆記工具**確保代理在多個會話中保留關鍵資訊。
*   ✅ **智慧上下文管理**：自動摘要對話歷史，以處理可配置代幣上限的上下文，實現無限長的任務。
*   ✅ **Claude Skills 整合**：包含 15 個專業技能，用於文件、設計、測試和開發。
*   ✅ **MCP 工具整合**：原生支援 MCP，可用於知識圖譜存取和網路搜尋等工具。
*   ✅ **全面的日誌記錄**：每個請求、響應和工具執行的詳細日誌，方便調試。
*   ✅ **簡潔優雅的設計**：美麗的 CLI 和易於理解的程式碼庫，是構建進階代理的理想起點。

## 目錄

- [Mini Agent](#mini-agent)
  - [目錄](#目錄)
  - [快速開始](#快速開始)
    - [1. 取得 API 金鑰](#1-取得-api-金鑰)
    - [2. 選擇您的使用模式](#2-選擇您的使用模式)
      - [🚀 快速開始模式（推薦給初學者）](#-快速開始模式推薦給初學者)
      - [🔧 開發模式](#-開發模式)
  - [ACP 與 Zed 編輯器整合（可選）](#acp-與-zed-編輯器整合可選)
  - [使用範例](#使用範例)
    - [任務執行](#任務執行)
    - [使用 Claude 技能（例如 PDF 產生）](#使用-claude-技能例如-pdf-產生)
    - [網路搜尋與摘要（MCP 工具）](#網路搜尋與摘要mcp-工具)
  - [測試](#測試)
    - [快速執行](#快速執行)
    - [測試覆蓋率](#測試覆蓋率)
  - [故障排除](#故障排除)
    - [SSL 憑證錯誤](#ssl-憑證錯誤)
    - [模組找不到錯誤](#模組找不到錯誤)
  - [相關文件](#相關文件)
  - [社群](#社群)
  - [貢獻](#貢獻)
  - [授權](#授權)
  - [參考文獻](#參考文獻)

## 快速開始

### 1. 取得 API 金鑰

MiniMax 提供全球和中國兩個平台。請根據您的網路環境選擇：

| 版本     | 平台                                                         | API Base                     |
| -------- | ------------------------------------------------------------ | ---------------------------- |
| **全球** | [https://platform.minimax.io](https://platform.minimax.io) | `https://api.minimax.io`     |
| **中國** | [https://platform.minimaxi.com](https://platform.minimaxi.com) | `https://api.minimaxi.com` |

**取得 API 金鑰的步驟：**
1. 訪問相應平台進行註冊和登入
2. 前往 **帳戶管理 > API 金鑰**
3. 點擊 **「建立新金鑰」**
4. 複製並安全保存（金鑰只會顯示一次）

> 💡 **提示**：記住您選擇的平台的 API Base 位址，設定時會需要用到

### 2. 選擇您的使用模式

**前置條件：安裝 uv**

兩種使用模式都需要 uv。如果尚未安裝：

```bash
# macOS/Linux/WSL
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
python -m pip install --user pipx
python -m pipx ensurepath
# 安裝後重啟 PowerShell

# 安裝完成後，重啟終端機或執行：
source ~/.bashrc  # 或 ~/.zshrc (macOS/Linux)
```

我們提供兩種使用模式——根據您的需求選擇：

#### 🚀 快速開始模式（推薦給初學者）

非常適合想要快速嘗試 Mini Agent 而不想複製儲存庫或修改程式碼的使用者。

**安裝：**

```bash
# 1. 直接從 GitHub 安裝
uv tool install git+https://github.com/MiniMax-AI/Mini-Agent.git

# 2. 執行設定腳本（自動建立設定檔）
# macOS/Linux:
curl -fsSL https://raw.githubusercontent.com/MiniMax-AI/Mini-Agent/main/scripts/setup-config.sh | bash

# Windows (PowerShell):
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/MiniMax-AI/Mini-Agent/main/scripts/setup-config.ps1" -OutFile "$env:TEMP\setup-config.ps1"
powershell -ExecutionPolicy Bypass -File "$env:TEMP\setup-config.ps1"
```

> 💡 **提示**：如果您想在本地開發或修改程式碼，請使用下面的「開發模式」

**設定：**

設定腳本會在 `~/.mini-agent/config/` 建立設定檔。編輯設定檔：

```bash
# 編輯設定檔
nano ~/.mini-agent/config/config.yaml
```

填入您的 API 金鑰和相應的 API Base：

```yaml
api_key: "YOUR_API_KEY_HERE"          # 步驟 1 的 API 金鑰
api_base: "https://api.minimax.io"  # 全球
# api_base: "https://api.minimaxi.com"  # 中國
model: "MiniMax-M2.5"
```

**開始使用：**

```bash
mini-agent                                    # 使用目前目錄作為工作區
mini-agent --workspace /path/to/your/project  # 指定工作區目錄
mini-agent --version                          # 檢查版本

# 管理命令
uv tool upgrade mini-agent                    # 升級到最新版本
uv tool uninstall mini-agent                  # 如有需要可解除安裝
uv tool list                                  # 查看所有已安裝的工具
```

#### 🔧 開發模式

適合需要修改程式碼、新增功能或除錯的開發者。

**安裝與設定：**

```bash
# 1. 複製儲存庫
git clone https://github.com/MiniMax-AI/Mini-Agent.git
cd Mini-Agent

# 2. 安裝 uv（如果還沒有的話）
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell):
irm https://astral.sh/uv/install.ps1 | iex
# 安裝後重啟終端機

# 3. 同步依賴
uv sync

# 替代方案：手動安裝依賴（如果不使用 uv）
# pip install -r requirements.txt
# 或安裝所需套件：
# pip install tiktoken pyyaml httpx pydantic requests prompt-toolkit mcp

# 4. 初始化 Claude 技能（可選）
git submodule update --init --recursive

# 5. 複製設定範本
```

**macOS/Linux：**
```bash
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

**Windows：**
```powershell
Copy-Item mini_agent\config\config-example.yaml mini_agent\config\config.yaml

# 6. 編輯設定檔
vim mini_agent/config/config.yaml  # 或使用您喜歡的編輯器
```

填入您的 API 金鑰和相應的 API Base：

```yaml
api_key: "YOUR_API_KEY_HERE"          # 步驟 1 的 API 金鑰
api_base: "https://api.minimax.io"  # 全球
# api_base: "https://api.minimaxi.com"  # 中國
model: "MiniMax-M2.5"
max_steps: 100
workspace_dir: "./workspace"
```

> 📖 完整設定指南：請參閱 [config-example.yaml](mini_agent/config/config-example.yaml)

**執行方式：**

選擇您偏好的執行方式：

```bash
# 方式 1：直接作為模組執行（適合除錯）
uv run python -m mini_agent.cli

# 方式 2：以可編輯模式安裝（推薦）
uv tool install -e .
# 安裝後可從任何地方執行，程式碼變更會立即生效
mini-agent
mini-agent --workspace /path/to/your/project
```

> 📖 更多開發指南，請參閱 [開發指南](docs/DEVELOPMENT_GUIDE.md)

> 📖 更多生產環境部署指南，請參閱 [生產指南](docs/PRODUCTION_GUIDE.md)

## ACP 與 Zed 編輯器整合（可選）

Mini Agent 支援[代理通訊協定（ACP）](https://github.com/modelcontextprotocol/protocol)，可與 Zed 等程式碼編輯器整合。

**在 Zed 編輯器中設定：**

1. 以開發模式或作為工具安裝 Mini Agent
2. 在您的 Zed `settings.json` 中新增：

```json
{
  "agent_servers": {
    "mini-agent": {
      "command": "/path/to/mini-agent-acp"
    }
  }
}
```

命令路徑應為：
- 如果透過 `uv tool install` 安裝：使用 `which mini-agent-acp` 的輸出
- 如果在開發模式： `./mini_agent/acp/server.py`

**使用方法：**
- 使用 `Ctrl+Shift+P` → "Agent: Toggle Panel" 開啟 Zed 的代理面板
- 在代理下拉選單中選擇「mini-agent」
- 直接在編輯器中與 Mini Agent 開始對話

## 使用範例

以下是 Mini Agent 可以做到的一些範例。

### 任務執行

*在此演示中，代理被要求建立一個簡單美觀的網頁並在瀏覽器中展示，展示了基本工具使用循環。*

![Demo GIF 1: Basic Task Execution](docs/assets/demo1-task-execution.gif "Basic Task Execution Demo")

### 使用 Claude 技能（例如 PDF 產生）

*這裡，代理利用 Claude 技能根據使用者請求建立專業文件（如 PDF 或 DOCX），展示其進階能力。*

![Demo GIF 2: Claude Skill Usage](docs/assets/demo2-claude-skill.gif "Claude Skill Usage Demo")

### 網路搜尋與摘要（MCP 工具）

*此演示展示了代理使用其網路搜尋工具在網路上尋找最新資訊並為您摘要。*

![Demo GIF 3: Web Search](docs/assets/demo3-web-search.gif "Web Search Demo")

## 測試

專案包含全面的測試案例，涵蓋單元測試、功能測試和整合測試。

### 快速執行

```bash
# 執行所有測試
pytest tests/ -v

# 執行核心功能測試
pytest tests/test_agent.py tests/test_note_tool.py -v
```

### 測試覆蓋率

- ✅ **單元測試** - 工具類別、LLM 用戶端
- ✅ **功能測試** - 對話筆記工具、MCP 載入
- ✅ **整合測試** - 代理端到端執行
- ✅ **外部服務** - Git MCP 伺服器載入


## 故障排除

### SSL 憑證錯誤

如果您遇到 `[SSL: CERTIFICATE_VERIFY_FAILED]` 錯誤：

**測試快速修復**（修改 `mini_agent/llm.py`）：
```python
# 第 50 行：在 AsyncClient 中加入 verify=False
async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
```

**生產環境解決方案：**
```bash
# 更新憑證
pip install --upgrade certifi

# 或設定系統 Proxy/憑證
```

### 模組找不到錯誤

請確保您是從專案目錄執行：
```bash
cd Mini-Agent
python -m mini_agent.cli
```

## 相關文件

- [開發指南](docs/DEVELOPMENT_GUIDE.md) - 詳細的開發和設定指南
- [生產指南](docs/PRODUCTION_GUIDE.md) - 生產環境部署的最佳實踐

## 社群

加入 MiniMax 官方社群以獲得幫助、分享想法並保持更新：

- **微信群**：掃描[聯絡我們](https://platform.minimaxi.com/docs/faq/contact-us)頁面上的 QR 碼加入

## 貢獻

歡迎提出問題和提交拉取請求！

- [貢獻指南](CONTRIBUTING.md) - 如何貢獻
- [行為準則](CODE_OF_CONDUCT.md) - 社群規範

## 授權

此專案根據 [MIT 授權](LICENSE) 授權。

## 參考文獻

- MiniMax API: https://platform.minimax.io/docs
- MiniMax-M2: https://github.com/MiniMax-AI/MiniMax-M2
- Anthropic API: https://docs.anthropic.com/claude/reference
- Claude Skills: https://github.com/anthropics/skills
- MCP Servers: https://github.com/modelcontextprotocol/servers

---

**⭐ 如果這個專案對您有幫助，請給它一個 Star！**