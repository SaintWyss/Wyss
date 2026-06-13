"""Tests de registry y extractores concretos."""

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest
from docx import Document
from openpyxl import Workbook  # type: ignore[import-untyped]
from PIL import Image

from core.domain.errors import ExtractionError, UnsupportedFileError
from core.domain.knowledge import ExtractedContent, SourceFile
from knowledge.extractors.docx import DocxExtractor
from knowledge.extractors.image import ImageExtractor
from knowledge.extractors.pdf import PdfExtractor
from knowledge.extractors.registry import ExtractorRegistry
from knowledge.extractors.spreadsheet import SpreadsheetExtractor
from knowledge.extractors.text import TextExtractor
from knowledge.extractors.video import VideoExtractor


def _source(path: Path, media_type: str) -> SourceFile:
    stat = path.stat()
    return SourceFile(
        path=str(path),
        media_type=media_type,
        size=stat.st_size,
        mtime=stat.st_mtime,
    )


class FakePrefixExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        return ExtractedContent(source=source, text="prefix", metadata={})


class FakeExactExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/x-exact"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        return ExtractedContent(source=source, text="exact", metadata={})


class FakeNewExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/x-wyss-future"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        return ExtractedContent(source=source, text="future", metadata={})


def test_registry_resolve_exact_and_prefix() -> None:
    registry = ExtractorRegistry()
    exact = FakeExactExtractor()
    prefix = FakePrefixExtractor()

    registry.register(exact)
    registry.register(prefix)

    assert registry.resolve("application/x-exact") is exact
    assert registry.resolve("text/plain") is prefix
    assert registry.resolve("application/unknown") is None


def test_new_extractor_no_pipeline_change() -> None:
    registry = ExtractorRegistry()
    extractor = FakeNewExtractor()

    registry.register(extractor)

    assert registry.resolve("application/x-wyss-future") is extractor


def test_pdf_extractor_extracts_text_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    doc: Any = fitz.open()  # type: ignore[no-untyped-call]
    page = doc.new_page()
    page.insert_text((72, 72), "hello pdf")
    doc.set_metadata({"title": "Title", "author": "Author"})
    doc.save(path)
    doc.close()

    content = PdfExtractor().extract(_source(path, "application/pdf"))

    assert "hello pdf" in content.text
    assert content.metadata["page_count"] == 1
    assert content.metadata["title"] == "Title"
    assert content.metadata["author"] == "Author"


def test_pdf_encrypted_raises_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.pdf"
    doc: Any = fitz.open()  # type: ignore[no-untyped-call]
    doc.new_page().insert_text((72, 72), "secret")
    encryption = fitz.PDF_ENCRYPT_AES_256  # type: ignore[attr-defined]
    doc.save(
        path,
        encryption=encryption,
        owner_pw="owner-password",
        user_pw="user-password",
        permissions=0,
    )
    doc.close()

    with pytest.raises(UnsupportedFileError):
        PdfExtractor().extract(_source(path, "application/pdf"))


def test_docx_extractor_extracts_paragraph_text(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("first paragraph")
    document.add_paragraph("second paragraph")
    document.save(str(path))

    content = DocxExtractor().extract(
        _source(
            path,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    assert "first paragraph" in content.text
    assert "second paragraph" in content.text
    assert content.metadata["paragraph_count"] == 2


def test_text_extractor_reads_utf8_with_replacement(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_bytes(b"print('hola')\n\xff")

    content = TextExtractor().extract(_source(path, "text/x-python"))

    assert "print('hola')" in content.text
    assert "\ufffd" in content.text


def test_spreadsheet_extractor_reads_csv(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("name,value\nalpha,1\n", encoding="utf-8")

    content = SpreadsheetExtractor().extract(_source(path, "text/csv"))

    assert "name\tvalue" in content.text
    assert "alpha\t1" in content.text
    assert content.metadata["row_count"] == 2


def test_spreadsheet_extractor_reads_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(["name", "value"])
    sheet.append(["alpha", 1])
    workbook.save(path)

    content = SpreadsheetExtractor().extract(
        _source(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )

    assert "[Data]" in content.text
    assert "alpha\t1" in content.text
    assert content.metadata["sheet_count"] == 1
    assert content.metadata["row_count"] == 2


def test_image_extractor_returns_metadata_only(tmp_path: Path) -> None:
    path = tmp_path / "sample.png"
    image = Image.new("RGB", (3, 2), color=(255, 0, 0))
    image.save(path)

    content = ImageExtractor().extract(_source(path, "image/png"))

    assert content.text == ""
    assert content.metadata["width"] == 3
    assert content.metadata["height"] == 2
    assert content.metadata["mode"] == "RGB"


def test_video_extractor_returns_ffprobe_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"fake")

    def fake_run(
        args: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert args[0] == "ffprobe"
        assert args[-1] == str(path)
        assert check is True
        assert capture_output is True
        assert text is True
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=0,
            stdout=(
                '{"format":{"duration":"1.25","format_name":"mov,mp4","bit_rate":"1000"},'
                '"streams":[{"codec_name":"h264","codec_type":"video"}]}'
            ),
        )

    monkeypatch.setattr("knowledge.extractors.video.subprocess.run", fake_run)

    content = VideoExtractor().extract(_source(path, "video/mp4"))

    assert content.text == ""
    assert content.metadata["duration"] == 1.25
    assert content.metadata["codec"] == "h264"
    assert content.metadata["codec_type"] == "video"


def test_corrupt_file_raises_extraction_error(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.png"
    path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ExtractionError):
        ImageExtractor().extract(_source(path, "image/png"))
