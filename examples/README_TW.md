# Mini Agent 範例

本目錄包含一系列循序漸進的範例，幫助您了解如何使用 Mini Agent 框架。

## 📚 範例列表

### 01_basic_tools.py - 基本工具使用

**難度**：⭐ 初學者

**內容**：
- 如何直接使用 ReadTool、WriteTool、EditTool、BashTool
- 不涉及 Agent 或 LLM，純粹的工具呼叫示範
- 非常適合了解每個工具的基本功能

**執行**：
```bash
python examples/01_basic_tools.py
```

**關鍵學習**：
- 工具輸入參數格式
- ToolResult 回傳結構
- 錯誤處理方法

---

### 02_simple_agent.py - 簡單 Agent 使用

**難度**：⭐⭐ 初學者至中級

**內容**：
- 建立最簡單的 Agent
- 讓 Agent 執行檔案建立任務
- 讓 Agent 執行 bash 命令任務
- 了解 Agent 執行流程

**執行**：
```bash
# 需要先設定 API 金鑰
python examples/02_simple_agent.py
```

**關鍵學習**：
- Agent 初始化流程
- 如何向 Agent 分配任務
- Agent 如何自主選擇工具
- 任務完成標準

**前置需求**：
- API 金鑰已設定在 `mini_agent/config/config.yaml`

---

### 03_session_notes.py - 會話記事工具

**難度**：⭐⭐⭐ 中級

**內容**：
- 直接使用會話記事工具（record_note、recall_notes）
- Agent 使用會話記事來維持跨會話記憶
- 展示兩個 Agent 實例如何共享記憶

**執行**：
```bash
python examples/03_session_notes.py
```

**關鍵學習**：
- 會話記事的工作原理
- 記事分類管理（category）
- 如何在系統提示中引導 Agent 使用記事
- 跨會話記憶實作

**亮點**：
這是此專案的核心功能之一！展示了一個輕量但有效的會話記憶管理解決方案。

---

### 04_full_agent.py - 功能完整的 Agent

**難度**：⭐⭐⭐⭐ 進階

**內容**：
- 完整設定包含所有功能的 Agent
- 整合基本工具 + 會話記事 + MCP 工具
- 複雜任務的完整執行流程
- 多輪對話範例

**執行**：
```bash
python examples/04_full_agent.py
```

**關鍵學習**：
- 如何組合多個工具
- MCP 工具的載入和使用
- 複雜任務的分解與執行
- 生產環境 Agent 設定

**前置需求**：
- API 金鑰已設定
- （可選）MCP 工具已設定

---

## 🚀 快速開始

### 1. 設定 API 金鑰

```bash
# 複製設定範本
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml

# 編輯設定檔並填入您的 MiniMax API 金鑰
vim mini_agent/config/config.yaml
```

### 2. 執行您的第一個範例

```bash
# 不需要 API 金鑰的範例
python examples/01_basic_tools.py

# 需要 API 金鑰的範例
python examples/02_simple_agent.py
```

### 3. 循序漸進的學習

建議按數字順序學習：
1. **01_basic_tools.py** - 了解工具
2. **02_simple_agent.py** - 了解 Agent
3. **03_session_notes.py** - 了解記憶管理
4. **04_full_agent.py** - 了解完整系統

---

## 📖 與測試案例的關係

這些範例都來自 `tests/` 目錄中的測試案例精煉而成：

| 範例               | 基於測試                                        | 描述                     |
| ------------------- | ---------------------------------------------------- | ------------------------------- |
| 01_basic_tools.py   | tests/test_tools.py                                  | 基本工具單元測試           |
| 02_simple_agent.py  | tests/test_agent.py                                  | Agent 基本功能測試 |
| 03_session_notes.py | tests/test_note_tool.py<br>tests/test_integration.py | 會話記事工具測試         |
| 04_full_agent.py    | tests/test_integration.py                            | 完整整合測試      |

---

## 💡 建議的學習路徑

### 路徑 1：快速開始
1. 執行 `01_basic_tools.py` - 了解工具
2. 執行 `02_simple_agent.py` - 執行您的第一個 Agent
3. 使用 `mini-agent` 直接進入互動模式

### 路徑 2：深入理解
1. 閱讀並執行所有範例（01 → 04）
2. 閱讀相應的測試案例（`tests/`）
3. 閱讀核心實作程式碼（`mini_agent/`）
4. 嘗試修改範例以實作您自己的功能

### 路徑 3：生產環境應用
1. 了解所有範例
2. 閱讀[生產部署指南](../docs/PRODUCTION_GUIDE.md)
3. 設定 MCP 工具和 Skills
4. 根據需求擴充工具集

---

## 🔧 疑難排解

### API 金鑰錯誤
```
❌ API key not configured in config.yaml
```
**解決方案**：確保您已在 `mini_agent/config/config.yaml` 中設定有效的 MiniMax API 金鑰

### 找不到 config.yaml
```
❌ config.yaml not found
```
**解決方案**：
```bash
cp mini_agent/config/config-example.yaml mini_agent/config/config.yaml
```

### MCP 工具載入失敗
```
⚠️ MCP tools not loaded: [error message]
```
**解決方案**：MCP 工具是可選的，不影響基本功能。如果您需要它們，請參考主要 README 中的 MCP 設定章節。

---

## 📚 更多資源

- [主要專案 README](../README.md) - 完整專案文件
- [測試案例](../tests/) - 更多使用範例
- [核心實作](../mini_agent/) - 原始碼
- [生產指南](../docs/PRODUCTION_GUIDE.md) - 部署指南

---

## 🤝 貢獻範例

如果您有好的使用範例，歡迎提交 PR！

建議的新範例方向：
- Web 搜尋整合範例（使用 MiniMax Search MCP）
- Skills 使用範例（文件處理、設計等）
- 自訂工具開發範例
- 錯誤處理和重試機制範例

---

**⭐ 如果這些範例對您有幫助，請給專案一個 Star！**