---
name: xlsx
description: "Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization. When Claude needs to work with spreadsheets (.xlsx, .xlsm, .csv, .tsv, etc) for: (1) Creating new spreadsheets with formulas and formatting, (2) Reading or analyzing data, (3) Modify existing spreadsheets while preserving formulas, (4) Data analysis and visualization in spreadsheets, or (5) Recalculating formulas"
license: Proprietary. LICENSE.txt has complete terms
---

# Requirements for Outputs

## All Excel files

### Zero Formula Errors
- Every Excel model MUST be delivered with ZERO formula errors (#REF!, #DIV/0!, #VALUE!, #N/A, #NAME?)

### Preserve Existing Templates (when updating templates)
- Study and EXACTLY match existing format, style, and conventions when modifying files
- Never impose standardized formatting on files with established patterns
- Existing template conventions ALWAYS override these guidelines

## Financial models

### Color Coding Standards
Unless otherwise stated by the user or existing template

#### Industry-Standard Color Conventions
- **Blue text (RGB: 0,0,255)**: Hardcoded inputs, and numbers users will change for scenarios
- **Black text (RGB: 0,0,0)**: ALL formulas and calculations
- **Green text (RGB: 0,128,0)**: Links pulling from other worksheets within same workbook
- **Red text (RGB: 255,0,0)**: External links to other files
- **Yellow background (RGB: 255,255,0)**: Key assumptions needing attention or cells that need to be updated

### Number Formatting Standards

#### Required Format Rules
- **Years**: Format as text strings (e.g., "2024" not "2,024")
- **Currency**: Use $#,##0 format; ALWAYS specify units in headers ("Revenue ($mm)")
- **Zeros**: Use number formatting to make all zeros "-", including percentages (e.g., "$#,##0;($#,##0);-")
- **Percentages**: Default to 0.0% format (one decimal)
- **Multiples**: Format as 0.0x for valuation multiples (EV/EBITDA, P/E)
- **Negative numbers**: Use parentheses (123) not minus -123

### Formula Construction Rules

#### Assumptions Placement
- Place ALL assumptions (growth rates, margins, multiples, etc.) in separate assumption cells
- Use cell references instead of hardcoded values in formulas
- Example: Use =B5*(1+$B$6) instead of =B5*1.05

#### Formula Error Prevention
- Verify all cell references are correct
- Check for off-by-one errors in ranges
- Ensure consistent formulas across all projection periods
- Test with edge cases (zero values, negative numbers)
- Verify no unintended circular references

#### Documentation Requirements for Hardcodes
- Comment or in cells beside (if end of table). Format: "Source: [System/Document], [Date], [Specific Reference], [URL if applicable]"
- Examples:
  - "Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]"
  - "Source: Bloomberg Terminal, 8/15/2025, AAPL US Equity"

---

# Technology Stack

**Runtime**: Python 3
**Primary Library**: openpyxl (Excel creation, styling, formulas, charts)
**Data Processing**: pandas (data manipulation, then export via openpyxl)
**Formula Recalculation**: `recalc.py` (LibreOffice-based, same directory as this skill)
**Static Validation**: `xlsx_validator.py` (same directory as this skill)

---

# Validation Tools

## 1. recalc.py — Formula Recalculation (LibreOffice)

Recalculates all formulas using LibreOffice and scans for Excel errors. **MANDATORY** after creating/modifying files with formulas.

```bash
python recalc.py output.xlsx [timeout_seconds]
```

Returns JSON:
```json
{
  "status": "success",
  "total_errors": 0,
  "total_formulas": 42,
  "error_summary": {}
}
```

- If `status` is `errors_found`, check `error_summary` for types and locations
- Fix errors and recalculate again until `total_errors` = 0

## 2. xlsx_validator.py — Static Analysis (5 Commands)

Performs static analysis without LibreOffice. Use as a complement to recalc.py or as standalone when LibreOffice is unavailable.

| Command | Purpose | When to Run |
|---------|---------|-------------|
| `recheck <file>` | Detect formula errors, zero-values, forbidden functions, implicit array formulas | After creating each sheet |
| `refcheck <file>` | Detect reference anomalies (out-of-range, header inclusion, insufficient range, pattern inconsistencies) | After creating each sheet |
| `inspect <file> --pretty` | Analyze file structure → JSON (sheets, headers, data ranges) | Before processing input files |
| `chart-verify <file>` | Verify all charts have actual data | After adding charts |
| `validate <file>` | Comprehensive pre-delivery validation | Before delivery |

```bash
python xlsx_validator.py recheck output.xlsx
python xlsx_validator.py refcheck output.xlsx
python xlsx_validator.py inspect input.xlsx --pretty
python xlsx_validator.py chart-verify output.xlsx
python xlsx_validator.py validate output.xlsx
```

---

# Excel Creation Workflow (MUST FOLLOW)

```
Phase 1: DESIGN
    → Plan all sheets: structure, formulas, cross-references BEFORE coding

Phase 2: CREATE & VALIDATE (Per-Sheet Loop)
    For each sheet:
        1. Create sheet (data, formulas, styling, charts if needed)
        2. Save workbook
        3. Run: recalc.py output.xlsx (if LibreOffice available)
        4. Run: xlsx_validator.py recheck output.xlsx
        5. Run: xlsx_validator.py refcheck output.xlsx
        6. Run: xlsx_validator.py chart-verify output.xlsx (if charts present)
        7. If errors found → Fix and repeat
        8. Only proceed to next sheet when current sheet has 0 errors

Phase 3: FINAL VALIDATION
    → Run: xlsx_validator.py validate output.xlsx
    → Exit code 0: Safe to deliver
    → Exit code non-zero: Fix and regenerate

Phase 4: DELIVER
    → Only deliver files that passed ALL validations
```

**FORBIDDEN Patterns:**
- Creating all sheets first, then running validation once at the end
- Ignoring errors and proceeding to next sheet
- Delivering files that failed validation

---

# CRITICAL: Use Formulas, Not Hardcoded Values

**Always use Excel formulas instead of calculating values in Python and hardcoding them.** The spreadsheet must remain dynamic and updateable.

```python
# CORRECT - Use Excel formulas
sheet['B10'] = '=SUM(B2:B9)'
sheet['C5'] = '=(C4-C2)/C2'
sheet['D20'] = '=AVERAGE(D2:D19)'
```

```python
# FORBIDDEN - Pre-calculate in Python and paste static values
total = df['Sales'].sum()
sheet['B10'] = total  # BAD: Static value, not a formula
```

**Only use static values when:**
- Data is fetched from external sources (web search, API)
- Values are constants that never change
- Formula would create circular reference

---

# Forbidden Functions (Incompatible with older Excel)

| Forbidden Function | Alternative |
|-------------------|-------------|
| `FILTER()` | AutoFilter, SUMIF/COUNTIF/INDEX-MATCH |
| `UNIQUE()` | Remove Duplicates, helper column with COUNTIF |
| `SORT()`, `SORTBY()` | Excel's Sort feature |
| `XLOOKUP()` | `INDEX()` + `MATCH()` |
| `XMATCH()` | `MATCH()` |
| `SEQUENCE()` | ROW() or manual fill |
| `LET()` | Helper cells for intermediate calculations |
| `LAMBDA()` | Named ranges or VBA |
| `RANDARRAY()` | `RAND()` with fill-down |

**Implicit Array Formula Detection:**
- Patterns like `MATCH(TRUE(), A1:A10>0, 0)` show #N/A in MS Excel
- Rewrite as: `=SUMPRODUCT((A1:A10>0)*ROW(A1:A10))-ROW(A1)+1`
- The `xlsx_validator.py recheck` command detects these automatically

---

# VLOOKUP Usage Rules

**When to Use**: Lookup/match/search tasks; multiple tables sharing keys; master-detail relationships; cross-file data with common keys

**Syntax**: `=VLOOKUP(lookup_value, table_array, col_index_num, FALSE)`
- Lookup column MUST be leftmost in table_array
- Use FALSE for exact match
- Lock range with `$A$2:$D$100`
- Wrap with `IFERROR(...,"N/A")`
- Cross-sheet: `Sheet2!$A$2:$C$100`
- **Alt**: INDEX/MATCH when lookup column is not leftmost

```python
ws['D2'] = '=IFERROR(VLOOKUP(A2,$G$2:$I$50,3,FALSE),"N/A")'
```

**FORBIDDEN**: Using Python merge() instead of VLOOKUP formulas for cross-table matching.

---

# External Data in Excel

When creating Excel files with externally fetched data:

- ALL external data MUST have source citations in the final Excel
- Use **two separate columns**: `Source Name` | `Source URL`
- Do NOT use HYPERLINK function (use plain text to avoid formula errors)
- If citation per-row is impractical, create a dedicated "Sources" sheet

---

# Style Rules

## Overall Visual Design Principles
- **MANDATORY: Hide Gridlines** on ALL sheets: `ws.sheet_view.showGridLines = False`
- Start data at B2 (top-left padding), not A1
- Title Row Height: `ws.row_dimensions[2].height = 30`
- Professional business-style color schemes, avoid over-decoration
- Consistency: uniform formatting, fonts, and color schemes
- Appropriate cell width/height — no imbalanced display scale

## Style Selection

### Minimalist Monochrome Style — DEFAULT for non-financial tasks

```python
# Base Colors (Black/White/Grey ONLY)
bg_white = "FFFFFF"
bg_light_grey = "F5F5F5"
bg_row_alt = "F9F9F9"
header_dark_grey = "333333"
text_dark = "000000"
border_grey = "D0D0D0"

# Blue Accent (ONLY color for differentiation)
blue_primary = "0066CC"
blue_secondary = "4A90D9"
blue_light = "E6F0FA"
```
- STRICTLY FORBIDDEN in monochrome style: Green, Red, Orange, Purple, Yellow, Pink, rainbow schemes

### Professional Finance Style — For financial/fiscal tasks

```python
bg_light = "ECF0F1"
text_dark = "000000"
accent_warm = "FFF3E0"
header_dark_blue = "1F4E79"
negative_red = "FF0000"
```

**Regional Financial Color Convention:**
| Region | Price Up | Price Down |
|--------|----------|------------|
| China (Mainland) | Red | Green |
| Outside China | Green | Red |

## Border Styles
- In general, do NOT add borders — keeps content focused
- Use borders only when needed to reflect calculation structure

## Merged Cells
```python
ws.merge_cells('B2:F2')
ws['B2'] = "Report Title"
ws['B2'].font = Font(size=18, bold=True)
ws['B2'].alignment = Alignment(horizontal='center', vertical='center')
```
- Use for: titles, section headers, category labels spanning columns
- Avoid in: data areas, formula ranges

## Conditional Formatting (Proactive Use Required)

```python
from openpyxl.formatting.rule import DataBarRule, ColorScaleRule, IconSetRule

# Data Bars on numeric columns
ws.conditional_formatting.add('C2:C100',
    DataBarRule(start_type='min', end_type='max', color='4A90D9', showValue=True))

# Color Scale for distribution
ws.conditional_formatting.add('D2:D100',
    ColorScaleRule(start_type='min', start_color='FFFFFF', end_type='max', end_color='4A90D9'))

# Icon Sets for KPIs
ws.conditional_formatting.add('E2:E100',
    IconSetRule(icon_style='3TrafficLights1', type='percent', values=[0, 33, 67], showValue=True))
```

---

# Cover Page Design

**Every Excel deliverable MUST include a Cover Page as the FIRST sheet.**

| Row | Content | Style |
|-----|---------|-------|
| 2-3 | Report Title | 18-20pt, Bold, Centered |
| 5 | Subtitle/Description | 12pt, Gray |
| 7-15 | Key Metrics Summary | Table with highlights |
| 17-20 | Sheet Index | All sheets with descriptions |
| 22+ | Notes & Instructions | Small font, Gray |

Required Elements:
1. **Report Title** — clear, descriptive
2. **Key Metrics Summary** — 3-6 most important numbers/findings
3. **Sheet Index** — navigation guide with sheet names and descriptions
4. **Cover styling**: clean white/light gray background, no gridlines, merged title area

---

# Visual Charts

## You MUST Create REAL Excel Charts

**Trigger Keywords**: "visual", "chart", "graph", "visualization", "diagram"

When a workbook has multiple datasets, ensure **each dataset has at least one chart** unless user says otherwise.

**FORBIDDEN:**
- Creating a "CHARTS DATA" sheet with instructions to insert charts manually
- Telling the user to create charts themselves

**REQUIRED:**
- Create embedded Excel charts using openpyxl.chart module
- Run `xlsx_validator.py chart-verify` after creating charts

```python
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList

chart = BarChart()
chart.type = "col"
chart.style = 10
chart.title = "Sales by Category"
chart.y_axis.title = 'Value'

data_ref = Reference(ws, min_col=2, min_row=1, max_row=4)
cats_ref = Reference(ws, min_col=1, min_row=2, max_row=4)
chart.add_data(data_ref, titles_from_data=True)
chart.set_categories(cats_ref)
ws.add_chart(chart, "E2")
```

**Chart Type Selection:**
| Data Type | Chart | Use Case |
|-----------|-------|----------|
| Trend | Line | Time series |
| Compare | Column/Bar | Category comparison |
| Composition | Pie/Doughnut | Percentages (6 items max) |
| Distribution | Histogram | Data spread |
| Correlation | Scatter | Relationships |

---

# Reading and Analyzing Data

## Data analysis with pandas
```python
import pandas as pd

df = pd.read_excel('file.xlsx')                          # First sheet
all_sheets = pd.read_excel('file.xlsx', sheet_name=None) # All sheets as dict

df.head()       # Preview
df.info()       # Column info
df.describe()   # Statistics

df.to_excel('output.xlsx', index=False)
```

## Creating new Excel files
```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
ws = wb.active
ws.sheet_view.showGridLines = False

ws['A1'] = 'Header'
ws['A1'].font = Font(bold=True, color='FFFFFF')
ws['A1'].fill = PatternFill('solid', start_color='333333')

ws['B2'] = '=SUM(A1:A10)'
ws.column_dimensions['A'].width = 20
wb.save('output.xlsx')
```

## Editing existing Excel files
```python
from openpyxl import load_workbook

wb = load_workbook('existing.xlsx')
ws = wb.active  # or wb['SheetName']

ws['A1'] = 'New Value'
ws.insert_rows(2)
new_sheet = wb.create_sheet('NewSheet')
wb.save('modified.xlsx')
```

---

# Best Practices

## Library Selection
- **pandas**: Best for data analysis, bulk operations, and simple data export
- **openpyxl**: Best for complex formatting, formulas, and Excel-specific features

## Working with openpyxl
- Cell indices are 1-based (row=1, column=1 = cell A1)
- Use `data_only=True` to read calculated values: `load_workbook('file.xlsx', data_only=True)`
- **Warning**: If opened with `data_only=True` and saved, formulas are permanently replaced with values
- Formulas are preserved but not evaluated — use recalc.py to update values

## Working with pandas
- Specify data types to avoid inference issues: `pd.read_excel('file.xlsx', dtype={'id': str})`
- For large files, read specific columns: `pd.read_excel('file.xlsx', usecols=['A', 'C', 'E'])`
- Handle dates properly: `pd.read_excel('file.xlsx', parse_dates=['date_column'])`

## Formula Verification Checklist

### Essential
- Test 2-3 sample references before building full model
- Column mapping: confirm Excel columns match (column 64 = BL, not BK)
- Row offset: Excel rows are 1-indexed (DataFrame row 5 = Excel row 6)

### Common Pitfalls
- NaN handling: check for null values with `pd.notna()`
- Division by zero: check denominators before using `/` in formulas
- Cross-sheet references: use correct format (`Sheet1!A1`)
- Off-by-one: verify formula ranges don't include headers or extend beyond data
- **Chinese vs English quotation marks**: Excel formulas ONLY accept English double quotes (`"`, Unicode U+0022). Chinese quotation marks (`"` left, `"` right, Unicode U+201C/U+201D) will cause #NAME? errors. Always verify quotes in IF statements and text formulas.
  - ❌ Wrong: `=IF(A1>30,"超过","正常")`  (Chinese quotes)
  - ✅ Correct: `=IF(A1>30,"超过","正常")` (English quotes)

## Code Style
- Write minimal, concise Python code
- Avoid verbose variable names and redundant operations
- For Excel files: add comments to cells with complex formulas, document data sources for hardcoded values

---

# Baseline Error Prevention

**Forbidden in deliverables:**
1. Formula errors: #VALUE!, #DIV/0!, #REF!, #NAME?, #NULL!, #NUM!, #N/A
2. Off-by-one references (wrong cell/row/column)
3. Text starting with `=` interpreted as formula
4. Static values instead of formulas for calculations
5. Placeholder text: "TBD", "Pending", "Manual calculation required"
6. Missing units in headers; inconsistent units
7. Currency without format symbols
8. Result of 0 must be verified — often indicates reference error

**Financial Values**: Store in smallest unit (15000000 not 1.5M). Use Excel format for display: `"$#,##0"` or `"¥#,##0"`.

---

# Final Checklist Before Delivery

1. Every sheet has content (not just headers)
2. All formula cells produce valid values (no errors, verify zeros)
3. Gridlines hidden on ALL sheets
4. Cover page present as first sheet
5. Charts verified with `chart-verify` (if applicable)
6. External data has source citations
7. Currency formatted with symbols for financial data
8. Cell dimensions are reasonable
9. Style matches task type (monochrome vs finance)
10. `recalc.py` returns `"status": "success"` (if LibreOffice available)
11. `xlsx_validator.py validate` returns exit code 0
