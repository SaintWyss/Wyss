"""Extractores concretos y registry para la capa de conocimiento."""

from knowledge.extractors.docx import DocxExtractor
from knowledge.extractors.image import ImageExtractor
from knowledge.extractors.pdf import PdfExtractor
from knowledge.extractors.registry import ExtractorRegistry
from knowledge.extractors.spreadsheet import SpreadsheetExtractor
from knowledge.extractors.text import TextExtractor
from knowledge.extractors.video import VideoExtractor

__all__ = [
    "DocxExtractor",
    "ExtractorRegistry",
    "ImageExtractor",
    "PdfExtractor",
    "SpreadsheetExtractor",
    "TextExtractor",
    "VideoExtractor",
]
