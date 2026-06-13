---
plan: 03-04
status: complete
---

# Plan 03-04 Summary

**One-liner:** Se construyó el scanner de filesystem con libmagic y el sistema registrable de extractores para PDF, DOCX, texto, planillas, imagen y video/audio.

## What was built
Task 1: Scanner + ExtractorRegistry
- `Scanner.scan()` recorre con `os.scandir`, resuelve y valida la raíz, omite dirs denylist, no sigue symlinks y detecta `media_type` con `magic.from_file(..., mime=True)`.
- `ScanItem` representa archivos procesables y skips permanentes; symlinks salen como `skipped_symlink` y archivos sobre límite como `skipped_size` con metadatos de `SourceFile`.
- `ExtractorRegistry` implementa plugin pattern con `register()` y `resolve()` por match exacto y prefijo MIME.
- Tests cubren denylist, symlinks, magic por contenido, límite de tamaño, resolución exacta/prefijo y extensibilidad sin tocar pipeline.

Task 2: Extractores concretos
- `PdfExtractor` usa PyMuPDF, extrae texto y metadata, y levanta `UnsupportedFileError` ante `doc.is_encrypted` sin autenticar ni pedir password.
- `DocxExtractor`, `TextExtractor` y `SpreadsheetExtractor` extraen texto de DOCX, texto/código, CSV y XLSX con `openpyxl` en `read_only=True`.
- `ImageExtractor` retorna `text=""` y metadata de Pillow + EXIF; `VideoExtractor` retorna `text=""` y metadata de `ffprobe` vía `subprocess.run(..., shell=False)`.
- Errores de parsing se traducen a `ExtractionError(path, error_type)`.

## Key files
### Created
- `src/knowledge/scanner.py` — scanner recursivo con denylist, symlinks, libmagic y límite de tamaño.
- `src/knowledge/extractors/__init__.py` — re-exports de registry y extractores, sin instanciación automática.
- `src/knowledge/extractors/registry.py` — registry registrable por MIME exacto/prefijo.
- `src/knowledge/extractors/pdf.py` — extractor PDF con manejo de encriptados.
- `src/knowledge/extractors/docx.py` — extractor DOCX.
- `src/knowledge/extractors/text.py` — extractor de texto, markdown y código textual.
- `src/knowledge/extractors/spreadsheet.py` — extractor CSV/XLSX.
- `src/knowledge/extractors/image.py` — extractor de metadatos de imagen.
- `src/knowledge/extractors/video.py` — extractor de metadatos de video/audio con ffprobe.
- `tests/knowledge/test_scanner.py` — tests del scanner.
- `tests/knowledge/extractors/test_extractors.py` — tests del registry y extractores.
- `.planning/phases/03-pipeline-de-ingesta/03-04-SUMMARY.md` — resumen de ejecución.

### Modified
- None.

## Decisions
- `ScanItem` incluye `path`, `status` opcional y `source` opcional; en `skipped_size` se conserva `SourceFile` para permitir indexación metadata-only posterior.
- El registry no instancia extractores; el bootstrap/composition root decidirá qué registrar.
- El test de video mockea `ffprobe` para verificar argumentos fijos, parseo JSON y ausencia de `shell=True` sin depender de assets pesados.

## Self-Check
- pytest: 230 passed / 2 skipped
- mypy: Success: no issues found in 106 source files
- ruff: All checks passed
- lint-imports: 2 contracts kept, 0 broken
