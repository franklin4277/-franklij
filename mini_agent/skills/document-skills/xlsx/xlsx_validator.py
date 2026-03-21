#!/usr/bin/env python3
"""
xlsx_validator.py - Excel file validation and inspection tool

Replaces KimiXlsx CLI for local use with Claude Code.

Commands:
  recheck          Detect formula errors, zero-value cells, implicit array formulas
  refcheck         Detect reference anomalies (out-of-range, header inclusion, etc.)
  inspect          Analyze Excel file structure → JSON
  chart-verify     Verify charts have actual data
  validate         Comprehensive pre-delivery validation

Usage:
  python3 xlsx_validator.py recheck output.xlsx
  python3 xlsx_validator.py refcheck output.xlsx
  python3 xlsx_validator.py inspect output.xlsx [--pretty]
  python3 xlsx_validator.py chart-verify output.xlsx
  python3 xlsx_validator.py validate output.xlsx
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import openpyxl
    from openpyxl.utils import get_column_letter, column_index_from_string
except ImportError:
    print("ERROR: openpyxl is required. Install with: pip install openpyxl")
    sys.exit(1)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

FORMULA_ERROR_VALUES = {
    "#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#NULL!", "#NUM!", "#N/A",
    "#GETTING_DATA", "#SPILL!", "#CALC!", "#BLOCKED!", "#UNKNOWN!",
}

FORBIDDEN_FUNCTIONS = {
    "FILTER", "UNIQUE", "SORT", "SORTBY", "XLOOKUP", "XMATCH",
    "SEQUENCE", "LET", "LAMBDA", "RANDARRAY", "ARRAYFORMULA",
    "QUERY", "IMPORTRANGE",
}

AGGREGATE_FUNCTIONS = {"SUM", "AVERAGE", "AVG", "COUNT", "COUNTA", "COUNTIF",
                       "SUMIF", "MIN", "MAX", "STDEV", "VAR", "MEDIAN"}

# Regex patterns
RE_CELL_REF = re.compile(
    r"(?:(?:'[^']+?'|[A-Za-z0-9_]+)!)?"  # optional sheet reference
    r"\$?([A-Z]{1,3})\$?(\d+)"            # column + row
)
RE_RANGE_REF = re.compile(
    r"(?:(?:'[^']+?'|[A-Za-z0-9_]+)!)?"
    r"\$?([A-Z]{1,3})\$?(\d+)"
    r":"
    r"\$?([A-Z]{1,3})\$?(\d+)"
)
# Version that also captures the sheet name for cross-sheet resolution
RE_RANGE_REF_WITH_SHEET = re.compile(
    r"(?:(?:'([^']+?)'|([A-Za-z0-9_]+))!)?"  # group 1=quoted sheet, group 2=unquoted sheet
    r"\$?([A-Z]{1,3})\$?(\d+)"               # group 3=col1, group 4=row1
    r":"
    r"\$?([A-Z]{1,3})\$?(\d+)"               # group 5=col2, group 6=row2
)
RE_FUNCTION_CALL = re.compile(r"([A-Z][A-Z0-9_.]+)\s*\(")
RE_IMPLICIT_ARRAY = re.compile(
    r"MATCH\s*\(\s*TRUE\s*\(\s*\)\s*,", re.IGNORECASE
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def col_to_idx(col_str):
    """Convert column letter(s) to 1-based index."""
    return column_index_from_string(col_str.upper())


def get_sheet_data_bounds(ws):
    """Return (min_row, max_row, min_col, max_col) of actual data in a sheet."""
    if ws.max_row is None or ws.max_column is None:
        return (1, 1, 1, 1)
    # Scan for actual data extent
    max_r, max_c = 0, 0
    min_r, min_c = ws.max_row + 1, ws.max_column + 1
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row,
                            min_col=1, max_col=ws.max_column):
        for cell in row:
            if cell.value is not None:
                r, c = cell.row, cell.column
                min_r = min(min_r, r)
                min_c = min(min_c, c)
                max_r = max(max_r, r)
                max_c = max(max_c, c)
    if max_r == 0:
        return (1, 1, 1, 1)
    return (min_r, max_r, min_c, max_c)


def extract_functions(formula):
    """Extract all function names from a formula string."""
    if not formula or not isinstance(formula, str) or not formula.startswith("="):
        return []
    return RE_FUNCTION_CALL.findall(formula)


def extract_ranges(formula):
    """Extract all range references (A1:B10) from a formula."""
    if not formula or not isinstance(formula, str):
        return []
    return RE_RANGE_REF.findall(formula)


def extract_ranges_with_sheet(formula):
    """Extract range references with their target sheet name.

    Returns list of (sheet_name_or_None, col1, row1, col2, row2).
    """
    if not formula or not isinstance(formula, str):
        return []
    results = []
    for m in RE_RANGE_REF_WITH_SHEET.finditer(formula):
        quoted_sheet, unquoted_sheet, c1, r1, c2, r2 = m.groups()
        sheet = quoted_sheet or unquoted_sheet  # None if same-sheet ref
        results.append((sheet, c1, r1, c2, r2))
    return results


def extract_cell_refs(formula):
    """Extract all individual cell references from a formula."""
    if not formula or not isinstance(formula, str):
        return []
    return RE_CELL_REF.findall(formula)


def is_formula(value):
    """Check if a cell value is a formula."""
    return isinstance(value, str) and value.startswith("=")


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_section(title):
    print(f"\n--- {title} ---")


def load_workbook_safe(filepath, data_only=False):
    """Load workbook with error handling."""
    try:
        return openpyxl.load_workbook(filepath, data_only=data_only)
    except Exception as e:
        print(f"ERROR: Cannot open '{filepath}': {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# Command: recheck
# ─────────────────────────────────────────────

def cmd_recheck(filepath):
    """Detect formula errors, zero-value cells, forbidden functions, and implicit array formulas."""
    print_header(f"RECHECK: {os.path.basename(filepath)}")

    wb_formula = load_workbook_safe(filepath, data_only=False)
    wb_data = load_workbook_safe(filepath, data_only=True)

    error_count = 0
    zero_count = 0
    forbidden_count = 0
    implicit_array_count = 0
    issues = []

    for sheet_name in wb_formula.sheetnames:
        ws_f = wb_formula[sheet_name]
        ws_d = wb_data[sheet_name]

        for row in ws_f.iter_rows(min_row=1, max_row=ws_f.max_row or 1,
                                  min_col=1, max_col=ws_f.max_column or 1):
            for cell in row:
                if not is_formula(cell.value):
                    continue

                formula = cell.value
                coord = f"'{sheet_name}'!{cell.coordinate}"

                # 1) Check cached value for errors
                data_cell = ws_d[cell.coordinate]
                if data_cell.value in FORMULA_ERROR_VALUES:
                    error_count += 1
                    issues.append({
                        "type": "formula_error",
                        "cell": coord,
                        "formula": formula,
                        "error": str(data_cell.value),
                    })
                elif isinstance(data_cell.value, str) and data_cell.value in FORMULA_ERROR_VALUES:
                    error_count += 1
                    issues.append({
                        "type": "formula_error",
                        "cell": coord,
                        "formula": formula,
                        "error": data_cell.value,
                    })

                # 2) Check for zero values in formula cells
                if data_cell.value == 0 or data_cell.value == 0.0:
                    zero_count += 1
                    issues.append({
                        "type": "zero_value",
                        "cell": coord,
                        "formula": formula,
                        "note": "Formula result is 0 - verify if this is expected",
                    })

                # 3) Check forbidden functions
                funcs = extract_functions(formula)
                for fn in funcs:
                    if fn.upper() in FORBIDDEN_FUNCTIONS:
                        forbidden_count += 1
                        issues.append({
                            "type": "forbidden_function",
                            "cell": coord,
                            "formula": formula,
                            "function": fn,
                        })

                # 4) Check implicit array formulas
                if RE_IMPLICIT_ARRAY.search(formula):
                    implicit_array_count += 1
                    issues.append({
                        "type": "implicit_array",
                        "cell": coord,
                        "formula": formula,
                        "note": "MATCH(TRUE(),...) pattern - may show #N/A in MS Excel. "
                                "Use SUMPRODUCT or helper column instead.",
                    })

    wb_formula.close()
    wb_data.close()

    # Also try LibreOffice recalculation if available
    lo_errors = _try_libreoffice_recheck(filepath)
    if lo_errors:
        for err in lo_errors:
            if not any(i["cell"] == err["cell"] and i["type"] == "formula_error" for i in issues):
                error_count += 1
                issues.append(err)

    # Report
    print_section("Summary")
    print(f"  formula_error_count : {error_count}")
    print(f"  zero_value_count    : {zero_count}")
    print(f"  forbidden_func_count: {forbidden_count}")
    print(f"  implicit_array_count: {implicit_array_count}")
    total = error_count + forbidden_count + implicit_array_count
    print(f"  total_errors        : {total}")

    if issues:
        print_section("Details")
        for i, issue in enumerate(issues, 1):
            tp = issue["type"].upper()
            cell = issue["cell"]
            formula = issue.get("formula", "")
            extra = issue.get("error") or issue.get("function") or issue.get("note", "")
            print(f"  [{i}] {tp} at {cell}")
            print(f"      Formula: {formula}")
            if extra:
                print(f"      Detail : {extra}")

    if total == 0 and zero_count == 0:
        print("\n  ✅ PASS - No errors detected")
    elif total == 0:
        print(f"\n  ⚠️  WARN - {zero_count} zero-value cells to verify (no hard errors)")
    else:
        print(f"\n  ❌ FAIL - {total} errors MUST be fixed before delivery")

    return total


def _try_libreoffice_recheck(filepath):
    """Attempt to recalculate with LibreOffice and check for errors."""
    lo_path = shutil.which("libreoffice") or shutil.which("soffice")
    if not lo_path:
        return []

    errors = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy file to temp
            tmp_file = os.path.join(tmpdir, os.path.basename(filepath))
            shutil.copy2(filepath, tmp_file)

            # Recalculate with LibreOffice
            subprocess.run(
                [lo_path, "--headless", "--calc", "--convert-to", "xlsx",
                 "--outdir", tmpdir, tmp_file],
                capture_output=True, timeout=60
            )

            # Re-read with data_only
            recalc_file = tmp_file  # LO overwrites in place with --convert-to same format
            if os.path.exists(recalc_file):
                wb = openpyxl.load_workbook(recalc_file, data_only=True)
                wb_f = openpyxl.load_workbook(recalc_file, data_only=False)
                for sn in wb.sheetnames:
                    ws_d = wb[sn]
                    ws_f = wb_f[sn]
                    for row_d, row_f in zip(
                        ws_d.iter_rows(min_row=1, max_row=ws_d.max_row or 1,
                                       min_col=1, max_col=ws_d.max_column or 1),
                        ws_f.iter_rows(min_row=1, max_row=ws_f.max_row or 1,
                                       min_col=1, max_col=ws_f.max_column or 1)):
                        for cd, cf in zip(row_d, row_f):
                            if is_formula(cf.value) and isinstance(cd.value, str) and cd.value in FORMULA_ERROR_VALUES:
                                errors.append({
                                    "type": "formula_error",
                                    "cell": f"'{sn}'!{cd.coordinate}",
                                    "formula": cf.value,
                                    "error": f"{cd.value} (LibreOffice recalc)",
                                })
                wb.close()
                wb_f.close()
    except Exception:
        pass  # LibreOffice check is best-effort

    return errors


# ─────────────────────────────────────────────
# Command: refcheck (reference-check)
# ─────────────────────────────────────────────

def cmd_refcheck(filepath):
    """Detect reference anomalies in formulas."""
    print_header(f"REFERENCE CHECK: {os.path.basename(filepath)}")

    wb = load_workbook_safe(filepath, data_only=False)
    issues = []

    # Pre-compute data bounds for ALL sheets so cross-sheet refs can be resolved
    all_sheet_bounds = {}
    for sn in wb.sheetnames:
        all_sheet_bounds[sn] = get_sheet_data_bounds(wb[sn])

    def resolve_bounds(target_sheet, current_sheet_name):
        """Get data bounds for the target sheet, falling back to current sheet."""
        if target_sheet and target_sheet in all_sheet_bounds:
            return all_sheet_bounds[target_sheet]
        return all_sheet_bounds.get(current_sheet_name, (1, 1, 1, 1))

    def resolve_ws(target_sheet, current_ws):
        """Get the worksheet object for the target sheet."""
        if target_sheet and target_sheet in wb.sheetnames:
            return wb[target_sheet]
        return current_ws

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row is None or ws.max_row <= 1:
            continue

        local_bounds = all_sheet_bounds[sheet_name]
        data_min_row, data_max_row, data_min_col, data_max_col = local_bounds

        # Collect formulas by column for pattern analysis
        col_formulas = defaultdict(list)

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row,
                                min_col=1, max_col=ws.max_column or 1):
            for cell in row:
                if not is_formula(cell.value):
                    continue

                formula = cell.value
                coord = f"'{sheet_name}'!{cell.coordinate}"
                col_formulas[cell.column].append((cell.row, cell.coordinate, formula))

                # Use sheet-aware range extraction
                ranges_with_sheet = extract_ranges_with_sheet(formula)

                # 1) Out-of-range references
                for (target_sheet, c1, r1, c2, r2) in ranges_with_sheet:
                    try:
                        end_row = int(r2)
                        tb = resolve_bounds(target_sheet, sheet_name)
                        target_max_row = tb[1]
                        # Flag if range extends more than 5x beyond target sheet's data
                        if end_row > target_max_row * 5 and end_row > target_max_row + 100:
                            target_label = f"'{target_sheet}'" if target_sheet else "current sheet"
                            issues.append({
                                "type": "out_of_range",
                                "cell": coord,
                                "formula": formula,
                                "detail": f"Range ends at row {end_row}, but {target_label} data ends at row {target_max_row}",
                            })
                    except ValueError:
                        pass

                # 2) Header row inclusion in aggregate functions
                funcs = extract_functions(formula)
                agg_funcs = [f for f in funcs if f.upper() in AGGREGATE_FUNCTIONS]
                if agg_funcs:
                    for (target_sheet, c1, r1, c2, r2) in ranges_with_sheet:
                        try:
                            start_row = int(r1)
                            if start_row == 1:
                                target_ws = resolve_ws(target_sheet, ws)
                                tb = resolve_bounds(target_sheet, sheet_name)
                                if tb[0] == 1:  # data starts at row 1
                                    col_idx = col_to_idx(c1)
                                    header_cell = target_ws.cell(row=1, column=col_idx)
                                    if isinstance(header_cell.value, str) and not header_cell.value.startswith("="):
                                        target_label = f"'{target_sheet}'!" if target_sheet else ""
                                        issues.append({
                                            "type": "header_inclusion",
                                            "cell": coord,
                                            "formula": formula,
                                            "detail": f"Aggregate function includes {target_label}row 1 (header: '{header_cell.value}')",
                                        })
                        except (ValueError, Exception):
                            pass

                # 3) Insufficient aggregate range (SUM/AVERAGE over ≤2 cells)
                if agg_funcs:
                    for (target_sheet, c1, r1, c2, r2) in ranges_with_sheet:
                        try:
                            row_span = abs(int(r2) - int(r1)) + 1
                            col_span = abs(col_to_idx(c2) - col_to_idx(c1)) + 1
                            total_cells = row_span * col_span
                            if total_cells <= 2:
                                issues.append({
                                    "type": "insufficient_range",
                                    "cell": coord,
                                    "formula": formula,
                                    "detail": f"Aggregate function covers only {total_cells} cell(s) "
                                              f"({c1}{r1}:{c2}{r2})",
                                })
                        except (ValueError, Exception):
                            pass

        # 4) Inconsistent formula patterns within a column
        #    Skip the last 1-2 rows of data — they are likely total/summary rows
        for col_idx, formulas_list in col_formulas.items():
            if len(formulas_list) < 3:
                continue

            # Identify the boundary: last row with a formula in this column
            max_formula_row = max(r for r, _, _ in formulas_list)

            # Normalize formulas: replace row numbers with placeholder
            def normalize_formula(f):
                return re.sub(r'(\$?)(\d+)', r'\1{R}', f)

            patterns = Counter()
            formula_map = {}
            for (r, coord_str, f) in formulas_list:
                norm = normalize_formula(f)
                patterns[norm] += 1
                if norm not in formula_map:
                    formula_map[norm] = []
                formula_map[norm].append((r, coord_str, f))

            if len(patterns) > 1:
                dominant_pattern = patterns.most_common(1)[0]
                dominant_norm, dominant_count = dominant_pattern
                for norm, entries in formula_map.items():
                    if norm != dominant_norm and len(entries) <= 2:
                        for (r, coord_str, f) in entries:
                            # Skip if this is a summary/total row (last 2 rows)
                            if r >= max_formula_row - 1:
                                continue
                            issues.append({
                                "type": "inconsistent_pattern",
                                "cell": f"'{sheet_name}'!{coord_str}",
                                "formula": f,
                                "detail": f"Deviates from dominant pattern in column "
                                          f"({dominant_count}/{len(formulas_list)} cells use a different pattern)",
                            })

    wb.close()

    # Report
    type_counts = Counter(i["type"] for i in issues)
    print_section("Summary")
    print(f"  out_of_range       : {type_counts.get('out_of_range', 0)}")
    print(f"  header_inclusion   : {type_counts.get('header_inclusion', 0)}")
    print(f"  insufficient_range : {type_counts.get('insufficient_range', 0)}")
    print(f"  inconsistent_pattern: {type_counts.get('inconsistent_pattern', 0)}")
    total = len(issues)
    print(f"  total_issues       : {total}")

    if issues:
        print_section("Details")
        for i, issue in enumerate(issues, 1):
            tp = issue["type"].upper()
            cell = issue["cell"]
            formula = issue.get("formula", "")
            detail = issue.get("detail", "")
            print(f"  [{i}] {tp} at {cell}")
            print(f"      Formula: {formula}")
            if detail:
                print(f"      Detail : {detail}")

    if total == 0:
        print("\n  ✅ PASS - No reference anomalies detected")
    else:
        print(f"\n  ⚠️  {total} potential reference issues found - please review")

    return total


# ─────────────────────────────────────────────
# Command: inspect
# ─────────────────────────────────────────────

def cmd_inspect(filepath, pretty=False):
    """Analyze Excel file structure and output JSON."""
    wb = load_workbook_safe(filepath, data_only=False)

    result = {
        "file": os.path.basename(filepath),
        "sheets": [],
    }

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        bounds = get_sheet_data_bounds(ws)
        min_r, max_r, min_c, max_c = bounds

        # Extract headers (first row of data)
        headers = []
        if ws.max_row and ws.max_row >= min_r:
            for col in range(min_c, max_c + 1):
                val = ws.cell(row=min_r, column=col).value
                headers.append(str(val) if val is not None else "")

        # Count formulas
        formula_count = 0
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row or 1,
                                min_col=1, max_col=ws.max_column or 1):
            for cell in row:
                if is_formula(cell.value):
                    formula_count += 1

        # Charts
        chart_count = len(ws._charts) if hasattr(ws, '_charts') else 0

        # Merged cells
        merged = [str(m) for m in ws.merged_cells.ranges]

        sheet_info = {
            "name": sheet_name,
            "dimensions": ws.dimensions,
            "data_range": {
                "start": f"{get_column_letter(min_c)}{min_r}",
                "end": f"{get_column_letter(max_c)}{max_r}",
            },
            "rows": max_r - min_r + 1 if max_r >= min_r else 0,
            "columns": max_c - min_c + 1 if max_c >= min_c else 0,
            "headers": headers,
            "formula_count": formula_count,
            "chart_count": chart_count,
            "merged_cells": merged if merged else [],
            "gridlines_hidden": not ws.sheet_view.showGridLines if ws.sheet_view else False,
        }
        result["sheets"].append(sheet_info)

    wb.close()

    if pretty:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = json.dumps(result, ensure_ascii=False)

    print(output)
    return result


# ─────────────────────────────────────────────
# Command: chart-verify
# ─────────────────────────────────────────────

def cmd_chart_verify(filepath):
    """Verify that all charts have actual data content."""
    print_header(f"CHART VERIFY: {os.path.basename(filepath)}")

    wb = load_workbook_safe(filepath, data_only=False)

    total_charts = 0
    empty_charts = 0
    chart_details = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        charts = ws._charts if hasattr(ws, '_charts') else []
        for idx, chart in enumerate(charts):
            total_charts += 1
            raw_title = chart.title
            if raw_title is None:
                title = f"(untitled chart #{idx+1})"
            elif isinstance(raw_title, str):
                title = raw_title
            else:
                # openpyxl Title object - extract text
                try:
                    title = raw_title.text if hasattr(raw_title, 'text') else str(raw_title)
                    # Try to get from rich text
                    if not isinstance(title, str) or 'object' in title:
                        for p in getattr(getattr(raw_title, 'tx', None), 'rich', None).p:
                            for run in p.r:
                                title = run.t
                                break
                            break
                except Exception:
                    title = f"Chart #{idx+1}"

            # Check if chart has data series
            has_data = False
            series_count = 0
            if hasattr(chart, 'series') and chart.series:
                series_count = len(chart.series)
                for s in chart.series:
                    if hasattr(s, 'val') and s.val is not None:
                        has_data = True
                        break
                    if hasattr(s, 'numRef') and s.numRef is not None:
                        has_data = True
                        break

            status = "OK" if has_data else "EMPTY"
            if not has_data:
                empty_charts += 1

            chart_details.append({
                "sheet": sheet_name,
                "title": title,
                "series_count": series_count,
                "status": status,
            })

    wb.close()

    # Report
    print_section("Summary")
    print(f"  total_charts : {total_charts}")
    print(f"  charts_ok    : {total_charts - empty_charts}")
    print(f"  charts_empty : {empty_charts}")

    if chart_details:
        print_section("Details")
        for cd in chart_details:
            status_icon = "✅" if cd["status"] == "OK" else "❌"
            print(f"  {status_icon} [{cd['sheet']}] {cd['title']} "
                  f"- {cd['series_count']} series - {cd['status']}")

    if total_charts == 0:
        print("\n  ⚠️  No charts found in workbook")
        return 1
    elif empty_charts > 0:
        print(f"\n  ❌ FAIL - {empty_charts} empty chart(s) detected. MUST FIX before delivery.")
        return 1
    else:
        print(f"\n  ✅ PASS - All {total_charts} chart(s) have data")
        return 0


# ─────────────────────────────────────────────
# Command: validate
# ─────────────────────────────────────────────

def cmd_validate(filepath):
    """Comprehensive pre-delivery validation."""
    print_header(f"VALIDATE: {os.path.basename(filepath)}")

    wb_f = load_workbook_safe(filepath, data_only=False)
    wb_d = load_workbook_safe(filepath, data_only=True)

    errors = []
    warnings = []

    for sheet_name in wb_f.sheetnames:
        ws_f = wb_f[sheet_name]
        ws_d = wb_d[sheet_name]

        has_any_data = False
        header_only = True

        for row in ws_f.iter_rows(min_row=1, max_row=ws_f.max_row or 1,
                                  min_col=1, max_col=ws_f.max_column or 1):
            for cell in row:
                if cell.value is not None:
                    has_any_data = True
                    if cell.row > 1:
                        header_only = False

                if not is_formula(cell.value):
                    continue

                formula = cell.value
                coord = f"'{sheet_name}'!{cell.coordinate}"

                # Check forbidden functions
                funcs = extract_functions(formula)
                for fn in funcs:
                    if fn.upper() in FORBIDDEN_FUNCTIONS:
                        errors.append(f"Forbidden function {fn}() at {coord}")

                # Check cached errors
                data_cell = ws_d[cell.coordinate]
                if data_cell.value in FORMULA_ERROR_VALUES:
                    errors.append(f"Formula error {data_cell.value} at {coord}")

                # Check implicit array formulas
                if RE_IMPLICIT_ARRAY.search(formula):
                    errors.append(
                        f"Implicit array formula at {coord} - will show #N/A in MS Excel"
                    )

                # Check for placeholder text
                if isinstance(cell.value, str):
                    lower = cell.value.lower()
                    for placeholder in ["tbd", "pending", "manual calculation required",
                                        "to be determined", "placeholder"]:
                        if placeholder in lower and not cell.value.startswith("="):
                            warnings.append(f"Placeholder text at {coord}: '{cell.value}'")

        # Check for empty sheets (has header but no data)
        if has_any_data and header_only and (ws_f.max_row or 0) <= 1:
            warnings.append(f"Sheet '{sheet_name}' appears to have only headers, no data rows")

    wb_f.close()
    wb_d.close()

    # Try to check .rels for absolute paths (zip inspection)
    try:
        import zipfile
        with zipfile.ZipFile(filepath, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.rels'):
                    content = zf.read(name).decode('utf-8', errors='ignore')
                    # Check for Windows absolute paths (C:\...) - these crash Excel
                    if re.search(r'Target\s*=\s*"[A-Za-z]:\\', content):
                        errors.append(f"Windows absolute path found in {name} - will crash Excel")
                    # Check for filesystem absolute paths (NOT internal /xl/... refs)
                    # Internal refs like /xl/worksheets/sheet1.xml are normal in OOXML
                    abs_matches = re.findall(r'Target\s*=\s*"(/[^"]+)"', content)
                    for m in abs_matches:
                        # Internal OOXML refs starting with /xl/, /docProps/, /_rels/ are normal
                        if not re.match(r'^/(xl|docProps|_rels|customXml)/', m):
                            errors.append(f"Absolute filesystem path in {name}: {m}")
    except Exception:
        warnings.append("Could not inspect ZIP structure for .rels validation")

    # Report
    print_section("Errors (MUST FIX)")
    if errors:
        for i, e in enumerate(errors, 1):
            print(f"  [{i}] ❌ {e}")
    else:
        print("  None")

    print_section("Warnings (Review)")
    if warnings:
        for i, w in enumerate(warnings, 1):
            print(f"  [{i}] ⚠️  {w}")
    else:
        print("  None")

    print_section("Result")
    if errors:
        print(f"  ❌ VALIDATION FAILED - {len(errors)} error(s)")
        print("  DO NOT deliver this file. Regenerate with fixes.")
        return 1
    elif warnings:
        print(f"  ⚠️  PASSED with {len(warnings)} warning(s) - review before delivery")
        return 0
    else:
        print("  ✅ VALIDATION PASSED - Safe to deliver")
        return 0


# ─────────────────────────────────────────────
# Main CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Excel file validation and inspection tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  recheck        Detect formula errors, zero-values, forbidden functions
  refcheck       Detect reference anomalies (out-of-range, header inclusion, etc.)
  inspect        Analyze file structure → JSON output
  chart-verify   Verify all charts have data
  validate       Comprehensive pre-delivery validation (run before delivery)

Examples:
  %(prog)s recheck output.xlsx
  %(prog)s refcheck output.xlsx
  %(prog)s inspect output.xlsx --pretty
  %(prog)s chart-verify output.xlsx
  %(prog)s validate output.xlsx
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # recheck
    p_recheck = subparsers.add_parser("recheck", help="Detect formula errors and zero-value cells")
    p_recheck.add_argument("file", help="Path to .xlsx file")

    # refcheck / reference-check
    p_refcheck = subparsers.add_parser("refcheck", aliases=["reference-check"],
                                       help="Detect reference anomalies")
    p_refcheck.add_argument("file", help="Path to .xlsx file")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Analyze file structure → JSON")
    p_inspect.add_argument("file", help="Path to .xlsx file")
    p_inspect.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    # chart-verify
    p_chart = subparsers.add_parser("chart-verify", help="Verify charts have data")
    p_chart.add_argument("file", help="Path to .xlsx file")

    # validate
    p_validate = subparsers.add_parser("validate", help="Comprehensive pre-delivery validation")
    p_validate.add_argument("file", help="Path to .xlsx file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    command = args.command
    if command in ("refcheck", "reference-check"):
        command = "refcheck"

    filepath = args.file
    if not os.path.isfile(filepath):
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    # Dispatch
    if command == "recheck":
        exit_code = cmd_recheck(filepath)
    elif command == "refcheck":
        exit_code = cmd_refcheck(filepath)
    elif command == "inspect":
        cmd_inspect(filepath, pretty=getattr(args, "pretty", False))
        exit_code = 0
    elif command == "chart-verify":
        exit_code = cmd_chart_verify(filepath)
    elif command == "validate":
        exit_code = cmd_validate(filepath)
    else:
        parser.print_help()
        exit_code = 1

    sys.exit(min(exit_code, 1))


if __name__ == "__main__":
    main()
