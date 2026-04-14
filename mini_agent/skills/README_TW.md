# Skills

Skills 是包含指令、腳本和資源的資料夾，Claude 可以動態載入這些內容以提升專業任務的效能。Skills 教導 Claude 如何以可重複的方式完成特定任務，無論是使用您公司的品牌指南建立文件、使用您組織的特定工作流程分析資料，或是自動化個人任務。

如需更多資訊，請參考：
- [什麼是 skills？](https://support.claude.com/en/articles/12512176-what-are-skills)
- [在 Claude 中使用 skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
- [如何建立自訂 skills](https://support.claude.com/en/articles/12512198-creating-custom-skills)
- [使用 Agent Skills 為現實世界配備代理](https://anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

# 關於此儲存庫

此儲存庫包含示範 Claude skills 系統功能的範例 skills。這些範例範圍廣泛，從創意應用（藝術、音樂、設計）到技術任務（測試 Web 應用程式、MCP 伺服器生成）再到企業工作流程（通訊、品牌等）。

每個 skill 都獨立存放在自己的目錄中，包含 `SKILL.md` 檔案，內含 Claude 使用的指令和中繼資料。瀏覽這些範例以取得建立您自己 skills 的靈感，或了解不同的模式和方法。

此儲存庫中的範例 skills 是開源的（Apache 2.0）。我們 also included the document creation & editing skills that power [Claude's document capabilities](https://www.anthropic.com/news/create-files) under the hood in the [`document-skills/`](./document-skills/) folder. These are source-available, not open source, but we wanted to share these with developers as a reference for more complex skills that are actively used in a production AI application.

**注意：**這些是作為靈感和學習的參考範例。它們展示的是通用功能，而非組織特定的工作流程或敏感內容。

## 免责声明

**這些 skills 僅提供用於示範和教育目的。** 雖然其中某些功能可能在 Claude 中可用，但您從 Claude 獲得的實作和行為可能與這些範例中顯示的有所不同。這些範例旨在說明模式和可能性。在依賴它們執行關鍵任務之前，請務必在您自己的環境中徹底測試 skills。

# 範例 Skills

此儲存庫包含各種展示不同功能的範例 skills：

## 創意與設計
- **algorithmic-art** - 使用 p5.js 建立生成藝術，包含 seeded randomness、flow fields 和粒子系統
- **canvas-design** - 使用設計理念在 .png 和 .pdf 格式中設計美麗的視覺藝術
- **slack-gif-creator** - 建立最佳化以符合 Slack 大小限制的動畫 GIF

## 開發與技術
- **artifacts-builder** - 使用 React、Tailwind CSS 和 shadcn/ui 元件建立複雜的 claude.ai HTML artifacts
- **mcp-server** - 建立高質量 MCP 伺服器的指南，用於整合外部 API 和服務
- **webapp-testing** - 使用 Playwright 測試本機 Web 應用程式，用於 UI 驗證和除錯

## 企業與通訊
- **brand-guidelines** - 將 Anthropic 的官方品牌顏色和字體應用於 artifacts
- **internal-comms** - 撰寫內部通訊，如狀態報告、電子報和常見問題
- **theme-factory** - 使用 10 種預設專業主題為 artifacts 設定樣式，或隨時產生自訂主題

## 元技能
- **skill-creator** - 建立有效延伸 Claude 能力的 skills 指南
- **template-skill** - 可作為建立新技能起點的基本範本

# Document Skills

`document-skills/` 子目錄包含 Anthropic 開發的 skills，幫助 Claude 建立各種文件檔案格式。這些 skills 展示了處理複雜檔案格式和二進位資料的進階模式：

- **docx** - 建立、編輯和分析 Word 文件，支援追蹤變更、註解、格式保留和文字擷取
- **pdf** - 全面的 PDF 處理工具包，用於擷取文字和表格、建立新 PDF、合併/分割文件和處理表單
- **pptx** - 建立、編輯和分析 PowerPoint 簡報，支援版面配置、範本、圖表和自動投影片生成
- **xlsx** - 建立、編輯和分析 Excel 試算表，支援公式、格式、資料分析和視覺化

**重要免责声明：**這些 document skills 是時間點快照，並非主動維護或更新。這些 skills 的版本隨 Claude 預先包含。它們主要作為參考範例，用來說明 Anthropic 如何開發更複雜的 skills 來處理二進位檔案格式和文件結構。

# 在 Claude Code、Claude.ai 和 API 中嘗試

## Claude Code

您可以透過在 Claude Code 中執行以下命令來註冊此儲存庫作為 Claude Code Plugin marketplace：
```
/plugin marketplace add anthropics/skills
```

然後，要安裝特定的 skills 組合：
1. 選擇 `Browse and install plugins`
2. 選擇 `anthropic-agent-skills`
3. 選擇 `document-skills` 或 `example-skills`
4. 選擇 `Install now`

或者，直接透過以下方式安裝任一 Plugin：
```
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

安裝外掛後，您可以透過提及它來使用 skill。例如，如果您從 marketplace 安裝了 `document-skills` 外掛，您可以要求 Claude Code 做類似這樣的事情：「使用 PDF skill 從 path/to/some-file.pdf 擷取表單欄位」

## Claude.ai

這些範例 skills 都已提供給 Claude.ai 的付費方案使用。

要使用此儲存庫中的任何 skill 或上傳自訂 skills，請參考[在 Claude 中使用 skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude#h_a4222fa77b)中的說明。

## Claude API

您可以使用 Anthropic 的預設 skills，並透過 Claude API 上傳自訂 skills。請參考 [Skills API 快速入門](https://docs.claude.com/en/api/skills-guide#creating-a-skill) 了解更多資訊。

# 建立基本 Skill

建立 skills 很簡單 - 只需要一個包含 `SKILL.md` 檔案的資料夾，該檔案包含 YAML frontmatter 和指令。您可以使用此儲存庫中的 **template-skill** 作為起點：

```markdown
---
name: my-skill-name
description: 清楚說明此 skill 的功能以及何時使用它
---

# My Skill Name

[在此新增 Claude 在此 skill 啟動時將遵循的指令]

## 範例
- 使用範例 1
- 使用範例 2

## 指南
- 指南 1
- 指南 2
```

frontmatter 只需要兩個欄位：
- `name` - 您的 skill 的唯一識別碼（使用小寫字母，空格用連字符）
- `description` - 完整說明 skill 的功能以及何時使用它

下方的 markdown 內容包含 Claude 將遵循的指令、範例和指南。如需更多詳細資訊，請參考[如何建立自訂 skills](https://support.claude.com/en/articles/12512198-creating-custom-skills)。

# 合作夥伴 Skills

Skills 是教導 Claude 如何更善於使用特定軟體工具的絕佳方式。當我們看到來自合作夥伴的精彩範例 skills 時，我們可能會在此處重點介紹其中一些：

- **Notion** - [Notion Skills for Claude](https://www.notion.so/notiondevs/Notion-Skills-for-Claude-28da4445d27180c7af1df7d8615723d0)