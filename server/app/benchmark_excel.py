"""Write a benchmark result ({"info", "tables"}, see benchmark.py) as a clean Excel file.

Sheets: "Info" (settings of the run) + one sheet per table ("Summary" first).
Each sheet: coloured bold header, frozen header row, filter buttons, sensible column widths,
numbers formatted (ms without decimals, scores with 2-3 decimals), and colours:
green = better / yes, red = worse / no / error. Similarity columns get a colour scale.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")  # dark blue
HEADER_FONT = Font(bold=True, color="FFFFFF")
GOOD_FILL = PatternFill("solid", fgColor="C6EFCE")    # light green
BAD_FILL = PatternFill("solid", fgColor="FFC7CE")     # light red
GOOD_VALUES = {"better", "kept"}
BAD_VALUES = {"worse", "dropped"}
# Only in these columns does "yes" mean good (in "safe_removed", "yes" is NOT good news).
YES_IS_GOOD_COLUMNS = {"correct", "correct_original", "correct_enhanced", "above_min_similarity"}
MAX_COLUMN_WIDTH = 60
LONG_TEXT_COLUMNS = ("answer", "ocr_text", "objects", "error", "reason", "embedded_text", "question", "note")


def build_workbook(result):
    """Return the .xlsx file as bytes."""
    workbook = Workbook()
    _write_info(workbook.active, result["info"])
    for name, rows in result["tables"].items():
        _write_table(workbook.create_sheet(name[:31]), rows)  # Excel sheet names: max 31 chars
    if "Summary" in workbook.sheetnames:
        workbook["Info"].sheet_view.tabSelected = False  # else Excel opens both sheets "grouped"
        workbook.active = workbook.sheetnames.index("Summary")  # open on the summary
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _write_info(sheet, info):
    """Sheet 'Info': one setting per line (benchmark type, date, question, models...)."""
    sheet.title = "Info"
    sheet.append(["Setting", "Value"])
    for key, value in info.items():
        sheet.append([key, value])
    _style_header(sheet, 2)
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 90


def _write_table(sheet, rows):
    """One table = one sheet. Columns = every key seen in the rows, in order of appearance."""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    sheet.append(columns)
    for row in rows:
        sheet.append([_cell_value(row.get(c)) for c in columns])
    _style_header(sheet, len(columns))
    sheet.freeze_panes = "A2"  # header stays visible when scrolling
    sheet.auto_filter.ref = sheet.dimensions
    for index, column in enumerate(columns, start=1):
        _style_column(sheet, index, column, len(rows))


def _cell_value(value):
    """Excel-friendly value: True/False → yes/no, None → empty cell."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return value


def _style_header(sheet, column_count):
    for cell in sheet[1][:column_count]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _style_column(sheet, index, column, row_count):
    """Width, number format, wrapping and colours of one column."""
    letter = get_column_letter(index)
    cells = [sheet.cell(row=r, column=index) for r in range(2, row_count + 2)]
    longest = max([len(str(column))] + [len(str(c.value)) for c in cells if c.value is not None])
    sheet.column_dimensions[letter].width = min(MAX_COLUMN_WIDTH, longest + 2)
    long_text = any(word in column for word in LONG_TEXT_COLUMNS)
    good = GOOD_VALUES | ({"yes"} if column in YES_IS_GOOD_COLUMNS else set())
    bad = BAD_VALUES | ({"no"} if column in YES_IS_GOOD_COLUMNS else set())
    for cell in cells:
        if column.endswith("_ms") or "_ms_" in column:
            cell.number_format = "#,##0"
        elif isinstance(cell.value, float):
            cell.number_format = "0.000" if ("sim" in column or "conf" in column) else "0.0"
        if long_text:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        if column == "error" and cell.value:
            cell.fill = BAD_FILL
        elif isinstance(cell.value, str) and cell.value in good:
            cell.fill = GOOD_FILL
        elif isinstance(cell.value, str) and cell.value in bad:
            cell.fill = BAD_FILL
    if column.startswith("sim: ") and row_count:  # similarity matrix: red (low) → green (high)
        sheet.conditional_formatting.add(
            f"{letter}2:{letter}{row_count + 1}",
            ColorScaleRule(start_type="num", start_value=0, start_color="F8696B",
                           mid_type="num", mid_value=0.25, mid_color="FFEB84",
                           end_type="num", end_value=0.6, end_color="63BE7B"))
