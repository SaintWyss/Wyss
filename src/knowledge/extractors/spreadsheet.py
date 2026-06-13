"""Extractores tabulares para CSV y XLSX."""

import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook  # type: ignore[import-untyped]

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SpreadsheetExtractor:
    """Convierte CSV/XLSX a texto tabular plano."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/csv", "application/csv", _XLSX_MIME})

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            if source.media_type == _XLSX_MIME:
                return self._extract_xlsx(source)
            return self._extract_csv(source)
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc

    def _extract_csv(self, source: SourceFile) -> ExtractedContent:
        with Path(source.path).open(encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.reader(handle))
        text = "\n".join("\t".join(row) for row in rows)
        return ExtractedContent(source=source, text=text, metadata={"row_count": len(rows)})

    def _extract_xlsx(self, source: SourceFile) -> ExtractedContent:
        workbook = load_workbook(source.path, read_only=True, data_only=True)
        try:
            lines: list[str] = []
            sheet_count = 0
            row_count = 0
            for sheet in workbook.worksheets:
                sheet_count += 1
                lines.append(f"[{sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    row_count += 1
                    lines.append("\t".join(_cell_to_text(cell) for cell in row))
            metadata: dict[str, object] = {
                "sheet_count": sheet_count,
                "row_count": row_count,
            }
            return ExtractedContent(source=source, text="\n".join(lines), metadata=metadata)
        finally:
            workbook.close()


def _cell_to_text(cell: Any) -> str:
    if cell is None:
        return ""
    return str(cell)
