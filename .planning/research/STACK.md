# Stack Research

**Proyecto:** Wyss — asistente operativo multi-agente, local-first
**Dimensión:** Stack (Python 2025/2026)
**Investigado:** 2026-06-10
**Confianza:** MEDIUM-HIGH (escrito inline desde conocimiento del ecosistema; versiones exactas a verificar con `uv add` en Fase 1 — los rangos indicados son conservadores)

---

## Recommended Stack (with versions)

### Core runtime

| Componente | Elección | Versión mínima | Rationale | Confianza |
|---|---|---|---|---|
| Python | CPython | 3.12+ (3.13 si estable en CachyOS) | `tomllib` nativo, type params PEP 695, perf | HIGH |
| Gestor deps | `uv` | latest | Lockfile robusto, 10-100x más rápido que pip, estándar de facto 2025 | HIGH |
| Build backend | `hatchling` | latest | Default de `uv init --package`, simple, sin magia | HIGH |

### Conocimiento e indexación

| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Vector store | **ChromaDB** (modo persistente embebido) | Sin servidor, API simple, colecciones por BC → mapea natural a habilitaciones | HIGH |
| Full-text | **SQLite FTS5** (stdlib `sqlite3`) | Cero deps, tokenizer unicode61, BM25 built-in | HIGH |
| PDF | **pymupdf** (fitz) | Mucho más rápido y robusto que pypdf/pdfplumber para volumen 2TB; AGPL — uso interno OK | HIGH |
| PDF fallback | `pdfplumber` | Para tablas complejas donde pymupdf falla | MEDIUM |
| DOCX | `python-docx` | Estándar, estable | HIGH |
| XLSX/CSV | `openpyxl` (read-only mode) + stdlib `csv` | read-only mode crítico para archivos grandes | HIGH |
| Imágenes (metadatos) | `Pillow` + `exifread` | Solo metadatos en v0.1 | HIGH |
| Video/audio (metadatos) | `pymediainfo` o `ffprobe` via subprocess | Solo metadatos en v0.1; ffprobe ya está en el sistema | MEDIUM |
| Detección de tipo | `python-magic` (libmagic) | No confiar en extensión; necesario para 2TB heterogéneos | HIGH |
| Detección de secretos | `detect-secrets` (Yelp) + reglas propias | Plugins de entropía + regex; complementar con denylist de rutas (.env, *.key, id_rsa) | HIGH |

### Embeddings (intercambiables vía port)

| Proveedor | Cliente | Nota |
|---|---|---|
| OpenAI | `openai` SDK | `text-embedding-3-small` — mejor costo/calidad para arranque |
| Voyage | `voyageai` | Mejor calidad para retrieval puro |
| Google | `google-genai` | Alternativa económica |

Port propio `EmbeddingProvider` (Protocol) — los SDKs viven solo en adapters. **No usar LangChain para esto** (dependencia pesada para lo que es una llamada HTTP).

### Daemon + IPC

| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| IPC | Unix socket + JSON-RPC 2.0 | stdlib `socket` + `json`; spec JSON-RPC es trivial de implementar (~100 líneas); evita dependencia de framework HTTP | HIGH |
| Event loop | `asyncio` (stdlib) | `asyncio.start_unix_server` hace el 90% del trabajo | HIGH |
| Supervisión | systemd user unit (`~/.config/systemd/user/wyss.service`) | Ya es el patrón del sistema del owner; restart automático, journal logging | HIGH |
| Scheduler | `APScheduler` 4.x (o 3.x estable si 4 sigue beta) | Cron triggers + persistencia de jobs; verificar estado de la 4.x al llegar a Fase 4 | MEDIUM |

### CLI

| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Framework | **Typer** | Type-hints driven, subcomandos limpios (`wyss index`, `wyss search`, `wyss ask`), built sobre Click | HIGH |
| Output | **Rich** | Tablas de resultados, progreso de indexación, paneles de confirmación B/C | HIGH |

### Config y validación

| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Formato | TOML (`tomllib` stdlib para leer) | Decisión tomada; stdlib desde 3.11 | HIGH |
| Validación | **Pydantic v2** | Validar config al boot (fail-fast), modelos de dominio serializables, `pydantic-settings` para .env | HIGH |

### Testing

| Componente | Elección | Rationale |
|---|---|---|
| Runner | `pytest` | Decisión tomada |
| Async | `pytest-asyncio` | Tests del daemon/orquestador |
| Fixtures FS | `tmp_path` built-in + factories propias | No usar pyfakefs — tests de integración reales sobre tmp |
| Mocks de API | `respx` (si httpx) o fixtures con adapters fake | El patrón hexagonal hace esto natural: inyectar `FakeEmbeddingProvider` |
| Lint/format | `ruff` (lint + format) | Único tool, reemplaza black+isort+flake8 |
| Types | `mypy` strict en `core/` | El núcleo hexagonal debe pasar strict; adapters pueden relajar |

---

## Validated Decisions

- **ChromaDB embebido** ✓ — correcto para single-owner local. Colección por BC = aislamiento natural para PermissionManager.
- **SQLite FTS5** ✓ — cero fricción, BM25 nativo. Híbrido FTS5+vector con fusión RRF (Reciprocal Rank Fusion) es el patrón estándar.
- **TOML** ✓ — `tomllib` stdlib.
- **uv** ✓ — estándar 2025.
- **Unix socket + JSON-RPC** ✓ — correcto. Evitar FastAPI/HTTP para IPC local: superficie innecesaria.
- **API-first embeddings** ✓ — correcto para v0.1 sin GPU dedicada al proyecto.

## Recommended Changes

1. **pymupdf en vez de pypdf2/pdfplumber como primario.** PyPDF2 está deprecado (renombrado pypdf, más lento). Para 2TB el throughput de extracción importa: pymupdf es ~10x más rápido. pdfplumber queda como fallback para tablas.
2. **Agregar Pydantic v2** — no estaba en las decisiones. Config validada al boot + modelos de dominio tipados. Sin esto, los errores de config aparecen en runtime profundo.
3. **Considerar `sqlite-vec` como alternativa futura a ChromaDB** — un solo archivo SQLite para FTS+vectores+metadata simplificaría backup/sync. No para v0.1 (ChromaDB más maduro), pero el port `VectorIndex` debe permitir el swap.

## Missing Pieces

- **`python-magic`** — detección de tipo real de archivo (no extensión). Crítico para 2TB heterogéneos.
- **`detect-secrets`** — base del filtro de secretos del pipeline (regla inviolable #8).
- **`watchdog`** — re-indexación incremental por eventos FS (opcional Fase 1, mencionado en prompt).
- **`tenacity`** — retry con backoff para llamadas a APIs de embeddings/LLM en el gateway.
- **`structlog`** — logging estructurado; el AuditLogger escribe a SQLite pero el log operativo necesita estructura.

## What NOT to Use

- **LangChain / LlamaIndex** — abstracción pesada que pelea contra la arquitectura hexagonal propia. Wyss define sus propios ports; estos frameworks imponen los suyos.
- **PyPDF2** — deprecado.
- **Celery / Redis** — overkill absoluto para daemon single-owner local.
- **FastAPI para IPC** — HTTP innecesario; superficie de ataque y dependencia extra.
- **python-daemon (PEP 3143)** — obsoleto; systemd user units hacen esto mejor en el entorno del owner.
- **SQLAlchemy ORM** — para el esquema de auditoría e índice, SQL directo con `sqlite3` stdlib es más simple y auditable. (Core queries son pocas y estables.)
