"""A small Excel workbook writer. Uses the standard library so the API image stays as it is."""

from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
import io


def _column(index: int) -> str:
    name = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell(column: int, row: int, value) -> str:
    ref = f"{_column(column)}{row}"
    if isinstance(value, bool):
        value = "yes" if value else "no"
    if isinstance(value, int) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    if isinstance(value, float):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = "" if value is None else str(value)
    if text[:1] in "=+-@\t\r":
        text = "'" + text
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _sheet(headers: list[str], rows: list[list]) -> str:
    body = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    body.append(
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews><sheetData>"
    )
    header_cells = "".join(_cell(index, 1, header) for index, header in enumerate(headers))
    body.append(f'<row r="1">{header_cells}</row>')
    for offset, row in enumerate(rows, start=2):
        cells = "".join(_cell(index, offset, value) for index, value in enumerate(row))
        body.append(f'<row r="{offset}">{cells}</row>')
    body.append("</sheetData></worksheet>")
    return "".join(body)


def workbook(sheets: list[tuple[str, list[str], list[list]]]) -> bytes:
    """Build an .xlsx file. Each sheet is a name, a header row, and data rows."""
    if not sheets:
        sheets = [("Report", ["Note"], [["Nothing to export."]])]
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
"""
            + "".join(
                f'  <Override PartName="/xl/worksheets/sheet{index}.xml" '
                f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
                for index in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        sheet_tags = []
        rels = []
        for index, (name, _headers, _rows) in enumerate(sheets, start=1):
            safe = escape(name[:31])
            sheet_tags.append(f'<sheet name="{safe}" sheetId="{index}" r:id="rId{index}"/>')
            rels.append(
                f'<Relationship Id="rId{index}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>"""
            + "".join(sheet_tags)
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">"""
            + "".join(rels)
            + '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            + "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>""",
        )
        for index, (_name, headers, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet(headers, rows))
    return buffer.getvalue()
