---
phase: 03-pipeline-de-ingesta
plan: 03-08
status: complete
requirements_covered:
  - KNOW-06
  - KNOW-07
---

# Plan 03-08 Summary

**One-liner:** Se agregaron extractores dedicados para HTML y RTF antes del SecretFilter, eliminando falsos positivos por data URIs/base64 y blobs hex embebidos sin debilitar la deteccion de secretos reales.

## What was built
Task 1: `src/knowledge/extractors/html.py` agrega `HtmlExtractor`, basado en `html.parser.HTMLParser`. Extrae texto escaneable sin markup ni atributos, ignora `script`/`style`, descarta data URIs y conserva comentarios para que secretos en comentarios no queden fuera del escaneo. El scanner real fue verificado empiricamente con archivos chicos: `.html` emite `text/html`.

Task 1 tambien agrega `src/knowledge/extractors/rtf.py` con `RtfExtractor`. Declara soporte para `text/rtf` y `application/rtf`; el scanner real fue verificado empiricamente y emitio `text/rtf` para `.rtf`. El extractor usa `striprtf` cuando esta instalado y tiene un fallback interno acotado para entornos offline/no-sync que elimina grupos `\pict`/`\object` y control words basicos, suficiente para evitar que blobs hex lleguen al SecretFilter durante la verificacion local.

Task 1 registra `HtmlExtractor` y `RtfExtractor` en el composition root `src/bootstrap/cli.py` mediante `_build_registry()`, y los exporta desde `src/knowledge/extractors/__init__.py`. `pipeline.py` no fue modificado.

Task 2: `tests/knowledge/extractors/test_extractors.py` agrega cobertura de cadena extractor -> `SecretFilter.check_content`: HTML con data URI base64 ya no dispara entropia tras extraccion; RTF con blob hex embebido ya no dispara entropia tras extraccion; un secreto `sk-ant-...` en texto visible HTML sigue detectandose; y un secreto `sk-ant-...` en comentario HTML tambien sigue detectandose.

## Key files
### Created
- `src/knowledge/extractors/html.py` - `HtmlExtractor`, texto HTML escaneable sin markup/scripts/styles/data URIs, con comentarios incluidos.
- `src/knowledge/extractors/rtf.py` - `RtfExtractor`, conversion RTF a texto plano usando `striprtf` cuando esta disponible.
- `.planning/phases/03-pipeline-de-ingesta/03-08-SUMMARY.md` - resumen de ejecucion del plan.

### Modified
- `src/knowledge/extractors/__init__.py` - exporta `HtmlExtractor` y `RtfExtractor`.
- `src/bootstrap/cli.py` - registra los dos extractores nuevos en `_build_registry()`.
- `pyproject.toml` - agrega dependencia `striprtf>=0.0.29`.
- `tests/knowledge/extractors/test_extractors.py` - agrega los 4 tests pedidos para FPs y secretos reales.

## Deviations From Plan
- `UV_CACHE_DIR=/tmp/uv-cache uv add striprtf` fue intentado, pero fallo por DNS/red restringida mientras resolvia PyPI. Se agrego `striprtf>=0.0.29` manualmente a `pyproject.toml`; el orquestador debera correr `uv sync`.
- Como `striprtf` no esta instalado en el entorno local no-sync, `RtfExtractor` incluye un fallback interno para poder verificar la conducta offline. Cuando `striprtf` este instalado, el extractor lo usa automaticamente mediante import dinamico.
- Los comandos exactos `UV_CACHE_DIR=/tmp/uv-cache uv run ...` no pudieron ejecutarse en verde porque uv intento resolver dependencias contra PyPI y fallo por DNS antes de correr pytest/mypy/ruff/import-linter. Se ejecuto la misma cadena con `--no-sync` contra el entorno existente.

## Verification Evidence
Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from knowledge.scanner import Scanner

with TemporaryDirectory() as td:
    root = Path(td)
    (root / 'sample.html').write_text('<!doctype html><html><body>Hello</body></html>', encoding='utf-8')
    (root / 'sample.rtf').write_text(r'{\rtf1\ansi Hello}', encoding='utf-8')
    for item in Scanner().scan(root, max_file_bytes=1000000, dir_denylist=frozenset()):
        assert item.source is not None
        print(Path(item.source.path).name, item.source.media_type)
PY
```

Output:
```text
sample.rtf text/rtf
sample.html text/html
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv add striprtf
```

Output:
```text
error: Request failed after 3 retries in 4.6s
  Caused by: Failed to fetch: `https://pypi.org/simple/pymupdf/`
  Caused by: error sending request for url (https://pypi.org/simple/pymupdf/)
  Caused by: client error (Connect)
  Caused by: dns error
  Caused by: failed to lookup address information: Temporary failure in name resolution
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/knowledge/extractors -q
```

Output:
```text
15 passed in 0.48s
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest -q && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync mypy && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check src tests && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync lint-imports
```

Output:
```text
263 passed, 3 skipped in 1.64s
Success: no issues found in 119 source files
All checks passed!
Contracts: 2 kept, 0 broken.
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/uv-cache uv run mypy
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
```

Output:
```text
pytest: failed before test execution trying to fetch https://pypi.org/simple/pytest/
mypy: failed before execution trying to fetch https://pypi.org/simple/pydantic/
ruff: failed before execution trying to fetch https://pypi.org/simple/rich/
lint-imports: failed before execution trying to fetch https://pypi.org/simple/exifread/
```

Command:
```bash
git diff -- src/knowledge/pipeline.py
```

Output:
```text

```

## Acceptance Coverage
- HTML con data URI base64 grande: `test_html_data_uri_not_flagged` prueba que el HTML crudo dispara `high_entropy`, pero el texto extraido conserva texto visible y ya no contiene el blob ni dispara `SecretFilter`.
- RTF con blob hex embebido: `test_rtf_hex_blob_not_flagged` prueba que el RTF crudo dispara `high_entropy`, pero el texto extraido conserva texto plano y ya no contiene el blob ni dispara `SecretFilter`.
- Secreto real en texto visible HTML: `test_html_real_secret_still_detected` detecta `("anthropic_key", "builtin_pattern")` tras extraccion.
- Secreto real en comentario HTML: `test_html_secret_in_comment_detected` conserva comentarios en el texto escaneado/indexado y detecta `("anthropic_key", "builtin_pattern")`.
- `HtmlExtractor` y `RtfExtractor` estan registrados solo en `src/bootstrap/cli.py`; `src/knowledge/pipeline.py` quedo sin cambios.
