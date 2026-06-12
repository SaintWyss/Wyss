# Phase 03: Pipeline de Ingesta — Research

**Researched:** 2026-06-12
**Domain:** Document ingestion pipeline — scanning, extraction, secret detection, FTS5 indexing, vector embedding (ChromaDB), incremental state management, CLI UX
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-27:** Archivo con secreto detectado → se excluye el ENTERO del índice. Sin redacción ni exclusión parcial.
- **D-28:** Reporte de exclusiones: resumen al final de la corrida + estado `excluded_secret` por archivo en SQLite + AuditEvent por cada exclusión.
- **D-29:** Detección en 3 capas: (1) denylist de rutas/extensiones; (2) reuso de `BUILTIN_SECRET_PATTERNS` de `src/gateway/secrets_patterns.py`; (3) detector de alta entropía.
- **D-30:** Allowlist por ruta/glob en `config.toml` que desactiva SOLO la capa de entropía. Las capas de patrones conocidos y denylist NUNCA se apagan.
- **D-31:** Pipeline completo en Fase 3: metadatos + FTS5 + chunking + embeddings a ChromaDB vía `OllamaEmbeddingProvider`.
- **D-32:** Ollama caído NO aborta la indexación: escaneo+extracción+FTS5 completa igual; archivos quedan `extracted` (sin `embedded`); re-run con Ollama vivo completa los pendientes.
- **D-33:** Estrategia de chunking (tamaño, overlap, por tipo): la decide el researcher/planner con defaults en `config.toml`.
- **D-34:** `--estimate` proyecta: N archivos nuevos/modificados, chunks proyectados, tamaño total, tiempo estimado de embedding local, "costo API: $0 (Ollama local)".
- **D-35:** Barra interactiva (librería elige planner) con etapa/archivo actual/N-total/ETA. En no-interactiva degrada a líneas de log cada N archivos.
- **D-36:** Errores por archivo NO cortan la corrida; archivo queda `failed` con error en SQLite. Aborta solo ante errores sistémicos.
- **D-37:** Re-run muestra conteo de skipped. `--dry-run` lista qué se indexaría y por qué.
- **D-38:** Exit codes: 0 si la corrida completó (aunque haya fallados); ≠0 solo si no pudo completar.
- **D-39:** Archivos `failed` se reintentan automáticamente, máximo 3 intentos; luego `--retry-failed` explícito.
- **D-40:** PDFs encriptados / formatos no soportados → `skipped_unsupported`. Sin pedir passwords.
- **D-41:** Límite de tamaño configurable en `config.toml`; archivos que lo excedan se indexan SOLO con metadatos.
- **D-42:** Symlinks NO se siguen; quedan `skipped_symlink`. Dirs ocultos y de ruido (`.git`, `node_modules`, etc.) excluidos por denylist configurable.

### Claude's Discretion

- Librería de barra de progreso (rich vs tqdm vs alternativa).
- Esquema exacto de la tabla de estado por archivo en SQLite.
- Umbral y algoritmo del detector de entropía.
- Cómo se nombra/selecciona la BC destino en el CLI.
- Defaults de chunking y límite de tamaño.
- Modo piloto automático: ante decisiones menores no listadas, tomar la opción recomendada sin preguntar; consultar solo ante cambios de arquitectura, seguridad o scope.

### Deferred Ideas (OUT OF SCOPE)

Ninguna — la discusión se mantuvo dentro del scope de la fase.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| KNOW-01 | `wyss index <ruta>` — escaneo, extracción e indexación híbrida (metadatos + FTS5 + vectores) | Scanner + ExtractorRegistry + FTS5Adapter + ChromaAdapter + CLI Typer |
| KNOW-02 | Re-indexación incremental: size+mtime filtro rápido, hash solo si cambió; 10 modificados no re-procesan 2 TB | `file_state` table con `size`, `mtime`, `sha256`; comparación lazy por orden |
| KNOW-03 | Escaneo reanudable: estado por archivo en SQLite; crash no pierde progreso | `file_state.status` columna + commit-por-archivo en WAL; el pipeline retoma desde `pending` |
| KNOW-06 | Extractores para PDF, DOCX, TXT, MD, PY/JS/TS, CSV, XLSX; imágenes y video/audio solo metadatos; registrables sin modificar pipeline | `ExtractorRegistry` con `register(extractor)` — plugin pattern (regla #9) |
| KNOW-07 | Secretos detectados y excluidos ANTES de indexar — verificado con prueba dirigida | 3-layer secret detector: ruta-denylist + BUILTIN_SECRET_PATTERNS + Shannon entropy |
| KNOW-08 | `wyss index --estimate` proyecta chunks y costo; `--dry-run` lista qué se indexaría | Recorrido de `file_state` + proyección de chunks sin llamar extractores |
| KNOW-09 | Indexación muestra progreso visible (archivos procesados / total, ETA) | Rich `Progress` con degradación a log en no-interactiva (sys.stdout.isatty()) |
| KNOW-11 | BC se organizan por contexto: colección separada por BC | `kb_id` como nombre de colección ChromaDB; `--bc <nombre>` CLI flag |
</phase_requirements>

---

## Summary

El pipeline de ingesta es el componente de mayor superficie de Fase 3: combina escaneo de filesystem, múltiples extractores de formato, detección de secretos en 3 capas, indexación FTS5 en SQLite, chunking configurable y embedding a ChromaDB, todo con estado por archivo persistido en SQLite para soporte incremental y reanudable.

La arquitectura ya está predefinida por las fases anteriores: el plugin pattern (`ExtractorRegistry`) está especificado en el spec canónico (regla #9), los ports de conocimiento ya existen en `core/ports/knowledge.py` (`Extractor`, `Chunker`, `EmbeddingProvider`, `FullTextIndex`, `VectorIndex`), y el `OllamaEmbeddingProvider` ya está implementado en `src/gateway/providers/ollama.py`. La fase construye las implementaciones concretas de esos ports y el composition root CLI.

La decisión técnica más importante para el planner: la tabla `file_state` en SQLite es el eje central del pipeline. Cada archivo pasa por estados `pending → extracted → embedded` (ruta feliz) o `failed`/`excluded_secret`/`skipped_*` (rutas de error). El commit por archivo (WAL) garantiza la reanudabilidad ante crash. Ollama puede estar caído — en ese caso los archivos quedan en `extracted` y un re-run completa los embeddings. Las 3 capas de detección de secretos deben ejecutarse ANTES de que el texto extraído toque ni FTS5 ni ChromaDB.

**Recomendación primaria:** Rich para progreso (D-35, ya en el STACK.md del owner), `chromadb>=1.5.9` PersistentClient para vectores, `pymupdf>=1.27` para PDF, detección de entropía con threshold base64≥4.5/hex≥3.0 (igual que detect-secrets de Yelp, configuración establecida en la industria).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Scanner de filesystem | `knowledge/scanner.py` | — | Recorre rutas, aplica denylist dirs/symlinks, produce SourceFile |
| Detección de secretos | `knowledge/secret_filter.py` | `gateway/secrets_patterns.py` (reuso) | Importa BUILTIN_SECRET_PATTERNS desde gateway; la lógica de filtro no vive en gateway |
| Plugin registry de extractores | `knowledge/extractors/registry.py` | `core/ports/knowledge.py` | Registro en memoria; los extractores implementan el Protocol `Extractor` |
| Extractores concretos | `knowledge/extractors/` | — | PDF, DOCX, TXT/MD/código, CSV, XLSX, imagen (metadatos), video (metadatos) |
| Chunker | `knowledge/chunker.py` | — | Implementa el Protocol `Chunker`; estrategia configurable |
| Estado por archivo (DB) | `knowledge/state_store.py` | SQLite WAL | Tabla `file_state`; espejo del patrón de `gateway/db.py` |
| FTS5 adapter | `knowledge/fts_index.py` | SQLite FTS5 | Implementa `FullTextIndex` port; external content table + triggers |
| Vector adapter | `knowledge/vector_index.py` | ChromaDB PersistentClient | Implementa `VectorIndex` port; colección por kb_id |
| Pipeline orchestration | `knowledge/pipeline.py` | — | Orquesta scanner → secret_filter → extractor → chunker → fts → embedder → vector |
| Embedding (async) | `gateway/providers/ollama.py` | — | Ya implementado en Fase 2; el pipeline lo inyecta |
| CLI entry point | `bootstrap/cli.py` | Typer + Rich | Composition root; wire todo; `wyss index <ruta>` |
| Config de ingesta | `bootstrap/config.py` | `config.toml [ingest]` | Sección `[ingest]` nueva en WyssConfigModel |

---

## Standard Stack

### Core (ya en pyproject.toml o aprobado en STACK.md)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12+ | Runtime | Fijado en pyproject.toml |
| sqlite3 | stdlib | FTS5 + state store | Cero deps, WAL nativo [VERIFIED: pyproject.toml] |
| pymupdf | ≥1.27.2 | PDF text extraction | Decisión D-2026-06-10 en STATE.md; 30-45x más rápido que alternativas [VERIFIED: PyPI] |
| python-docx | ≥1.2.0 | DOCX extraction | Estándar, estable [VERIFIED: PyPI] |
| openpyxl | ≥3.1.5 | XLSX extraction (read-only) | Solo lectura en archivos grandes [VERIFIED: PyPI] |
| python-magic | ≥0.4.27 | MIME type detection from bytes | No confiar en extensión para 2TB heterogéneos; libmagic.so.1 presente en sistema [VERIFIED: PyPI + ldconfig] |
| chromadb | ≥1.5.9 | Vector store (embedded persistent) | Decisión fijada en spec canónico; API 1.x estable [VERIFIED: PyPI] |
| rich | ≥15.0.0 | Progress bar + output formatting | Elegido en STACK.md del owner; D-35 dice "librería elige planner" [VERIFIED: PyPI] |
| typer | ≥0.26.7 | CLI framework | Elegido en STACK.md; type-hints driven [VERIFIED: PyPI] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pillow | ≥12.2.0 | Imagen metadatos (EXIF width/height/mode) | Archivos image/* — solo metadatos en v0.1 [VERIFIED: PyPI] |
| exifread | ≥3.5.1 | EXIF detallado de JPG/TIFF | Complementa Pillow para metadatos ricos [VERIFIED: PyPI] |
| pymediainfo | ≥7.0.1 | Video/audio metadatos | Archivos video/* y audio/* — wrappea mediainfo CLI [VERIFIED: PyPI] |

**Nota sobre pymediainfo:** Requiere `mediainfo` CLI instalado. `mediainfo` NO está en el sistema (`command -v mediainfo` no encontrado). `ffprobe` SÍ está disponible (`/usr/bin/ffprobe`, version n8.1.1). El planner debe decidir: instalar `mediainfo` vía pacman, o implementar el extractor de video metadatos directamente con `subprocess ffprobe`. Recomendación: usar `subprocess ffprobe` para no agregar dependencia extra — ya está instalado y es más robusto.

### Dependencias que NO se instalan (ya disponibles)

| Recurso | Disponible | Cómo |
|---------|-----------|------|
| `OllamaEmbeddingProvider` | Ya en `src/gateway/providers/ollama.py` | Reusar directamente |
| `BUILTIN_SECRET_PATTERNS` | Ya en `src/gateway/secrets_patterns.py` | Importar desde ahí |
| `open_gateway_db` pattern | Ya en `src/gateway/db.py` | Replicar el patrón para `index.db` |
| libmagic.so.1 | Sistema: `/usr/lib/libmagic.so.1` | Linkea python-magic |
| ffprobe | Sistema: `/usr/bin/ffprobe` v8.1.1 | Video/audio metadata via subprocess |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Rich Progress | tqdm | Rich ya está en el stack; tqdm es más simple pero menor integración con Rich tables/panels |
| pymupdf | pdfplumber | pdfplumber para tablas complejas, pero más lento — usar como fallback en el extractor PDF si pymupdf retorna vacío |
| python-magic | imghdr+mimetypes | python-magic usa los bytes reales del archivo; mimetypes solo mira la extensión — inaceptable para 2TB heterogéneos |
| pymediainfo | subprocess ffprobe | ffprobe ya instalado → usar subprocess; evita dependencia de sistema `mediainfo` |

**Installation:**

```bash
uv add "pymupdf>=1.27.2" "python-docx>=1.2.0" "openpyxl>=3.1.5" "python-magic>=0.4.27" "chromadb>=1.5.9" "rich>=15.0.0" "typer>=0.26.7" "pillow>=12.2.0" "exifread>=3.5.1"
```

**Nota:** `pymediainfo` NO se agrega — se usa `ffprobe` vía subprocess. `detect-secrets` NO se agrega — la detección de entropía se implementa directamente (ver sección Secret Detection).

---

## Package Legitimacy Audit

| Package | Registry | slopcheck | Disposition |
|---------|----------|-----------|-------------|
| pymupdf | PyPI | [OK] | Approved |
| chromadb | PyPI | [OK] | Approved |
| python-docx | PyPI | [OK] — nota: "classic LLM naming pattern but established" | Approved |
| openpyxl | PyPI | [OK] | Approved |
| python-magic | PyPI | [OK] — nota: "classic LLM naming pattern but established" | Approved |
| rich | PyPI | [OK] | Approved |
| typer | PyPI | [OK] | Approved |
| pillow | PyPI | [OK] | Approved |
| exifread | PyPI | [OK] | Approved |
| pymediainfo | PyPI | [OK] | NOT ADDED — usar ffprobe vía subprocess |
| detect-secrets | PyPI | [OK] | NOT ADDED — entropía implementada directamente |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*Todos los paquetes pasaron slopcheck 0.6.1 [OK]. slopcheck fue corrido el 2026-06-12.*

---

## Architecture Patterns

### System Architecture Diagram

```
wyss index <ruta> [--bc <nombre>] [--estimate] [--dry-run] [--retry-failed]
         │
         ▼ bootstrap/cli.py (composition root — wire all adapters)
         │
         ▼ knowledge/pipeline.py  ←── inyecta: scanner, secret_filter,
         │                              registry, chunker, state_store,
         │                              fts_index, embedder, vector_index, audit
         │
    ┌────┴─────┐
    │  SCAN    │ knowledge/scanner.py
    │          │ os.scandir() → aplica dir_denylist, symlinks, tamaño
    │          │ produce SourceFile (path, media_type, size, mtime)
    └────┬─────┘
         │ SourceFile
         ▼
    ┌────┴─────┐
    │  STATE   │ knowledge/state_store.py → SQLite WAL (index.db)
    │  CHECK   │ SELECT status, size, mtime, sha256 WHERE path = ?
    │          │ → skip si size+mtime igual Y sha256 igual
    │          │ → pending si nuevo o modificado
    └────┬─────┘
         │ (solo archivos pending/failed-with-retries)
         ▼
    ┌────┴─────┐
    │  SECRET  │ knowledge/secret_filter.py
    │  FILTER  │ Capa 1: path/extension denylist (.env*, *.key, *.pem, id_rsa, ...)
    │  (pre-   │ Capa 2: magic.from_file() → extractor → BUILTIN_SECRET_PATTERNS scan
    │  extract)│ Capa 3: Shannon entropy ≥4.5 (base64) / ≥3.0 (hex) en tokens ≥20 chars
    │          │ → EXCLUYE ARCHIVO ENTERO si match (D-27); AuditEvent + excluded_secret
    └────┬─────┘
         │ (archivos limpios)
         ▼
    ┌────┴─────┐
    │  EXTRACT │ knowledge/extractors/registry.py → Extractor (Plugin Pattern)
    │          │ media_type → extractor.extract(source) → ExtractedContent
    │          │ Si falla → status=failed, attempts++, sigue
    └────┬─────┘
         │ ExtractedContent
         ▼
    ┌────┴─────┐
    │  CHUNK   │ knowledge/chunker.py → Sequence[Chunk]
    │          │ Estrategia: overlap-window de tokens (512 tokens, 10% overlap)
    │          │ por tipo: texto/código/markdown — configurable en [ingest]
    └────┬─────┘
         │ Sequence[Chunk] + IndexEntry (con kb_id)
         ├──────────────────────────────────────┐
         ▼                                      ▼
    ┌────┴─────┐                          ┌─────┴────┐
    │  FTS5    │ knowledge/fts_index.py   │  EMBED   │ OllamaEmbeddingProvider
    │  UPSERT  │ SQLite FTS5              │  (async) │ POST /api/embed (batch)
    │          │ status → extracted       │          │ Si Ollama DOWN → log + skip
    └──────────┘                          └─────┬────┘
                                                │ Sequence[Vector]
                                                ▼
                                          ┌─────┴────┐
                                          │  CHROMA  │ knowledge/vector_index.py
                                          │  UPSERT  │ collection(kb_id).upsert(...)
                                          │          │ status → embedded
                                          └──────────┘
```

**Nota sobre secret detection timing:** La capa 2 (pattern scan sobre contenido) requiere extraer el texto primero — el pipeline extrae a un buffer temporal, escanea secretos, y SOLO si está limpio escribe al FTS5/ChromaDB. El texto nunca toca el índice si hay un match.

### Recommended Project Structure

```
src/knowledge/
├── __init__.py                   # módulo existente (scaffold vacío)
├── pipeline.py                   # orquestador principal
├── scanner.py                    # walk filesystem, producir SourceFile
├── secret_filter.py              # 3-layer detection, importa BUILTIN_SECRET_PATTERNS
├── chunker.py                    # implementa Chunker port; configurable
├── state_store.py                # SQLite WAL (index.db) — estados por archivo
├── fts_index.py                  # implementa FullTextIndex port (FTS5)
├── vector_index.py               # implementa VectorIndex port (ChromaDB)
└── extractors/
    ├── __init__.py
    ├── registry.py               # ExtractorRegistry — plugin register/resolve
    ├── pdf.py                    # pymupdf; fallback pdfplumber para tablas
    ├── docx.py                   # python-docx
    ├── text.py                   # TXT, MD, PY, JS, TS (text/*)
    ├── spreadsheet.py            # CSV (stdlib) + XLSX (openpyxl read-only)
    ├── image.py                  # Pillow + exifread — solo metadatos
    └── video.py                  # subprocess ffprobe — solo metadatos

src/bootstrap/
└── cli.py                        # Typer app; "wyss index" command; composition root

tests/knowledge/
├── __init__.py
├── conftest.py                   # fixtures: tmp_path DB, fake extractors, fixture BCs
├── test_scanner.py               # KNOW-01: scan paths, denylist dirs, symlinks
├── test_secret_filter.py         # KNOW-07: directed tests; plantilla secreta → no aparece
├── test_state_store.py           # KNOW-02 + KNOW-03: incremental + reanudable
├── test_chunker.py               # KNOW-01: chunks generados correctamente
├── test_fts_index.py             # KNOW-01: upsert + search FTS5
├── test_vector_index.py          # KNOW-11: colección por kb_id
├── test_pipeline.py              # KNOW-03: crash-resume; KNOW-06: plugin extensibility
└── extractors/
    ├── test_pdf_extractor.py     # encrypted detection → skipped_unsupported
    ├── test_docx_extractor.py
    ├── test_text_extractor.py
    ├── test_spreadsheet_extractor.py
    └── test_image_extractor.py
tests/cli/
└── test_index_command.py         # KNOW-08: --estimate; KNOW-09: progress; exit codes
```

### Pattern 1: ExtractorRegistry — Plugin Pattern (regla #9)

**What:** El pipeline recibe un `ExtractorRegistry` inyectado. Agregar un extractor = llamar `registry.register(extractor)` en el composition root, sin tocar el pipeline.

**When to use:** Siempre. La extensibilidad sin ruptura (regla #9) es un criterio de aceptación explícito (criterio 6 del roadmap).

**Example:**

```python
# Source: docs/18-prompt-implementacion.md — Plugin Pattern
class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: list[Extractor] = []

    def register(self, extractor: Extractor) -> None:
        self._extractors.append(extractor)

    def resolve(self, media_type: str) -> Extractor | None:
        for ext in self._extractors:
            if media_type in ext.media_types:
                return ext
        return None
```

### Pattern 2: File State Machine en SQLite

**What:** La tabla `file_state` es el eje del pipeline incremental y reanudable.

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS file_state (
    path       TEXT PRIMARY KEY,
    kb_id      TEXT NOT NULL,
    size       INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    sha256     TEXT,                   -- NULL hasta que size+mtime cambió
    status     TEXT NOT NULL DEFAULT 'pending',
    -- Estados: pending|extracted|embedded|failed|excluded_secret
    --          |skipped_unsupported|skipped_symlink|skipped_size
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,                   -- último error si status=failed
    indexed_at REAL,                   -- epoch cuando llegó a embedded
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_file_state_status ON file_state(status);
CREATE INDEX IF NOT EXISTS idx_file_state_kb ON file_state(kb_id);
```

**Incremental check (KNOW-02):**

```python
# Source: [ASSUMED] — patrón propio derivado de requisito KNOW-02
def needs_reindex(self, path: str, size: int, mtime: float) -> bool:
    row = self._conn.execute(
        "SELECT size, mtime, sha256, status FROM file_state WHERE path = ?", (path,)
    ).fetchone()
    if row is None:
        return True  # nuevo archivo
    stored_size, stored_mtime, stored_sha256, status = row
    if status == "embedded":
        if size == stored_size and mtime == stored_mtime:
            return False  # fast path: sin cambios
        # size o mtime cambiaron → verificar sha256
        current_sha256 = compute_sha256(path)
        return current_sha256 != stored_sha256
    return True  # pending/extracted/failed → procesar
```

### Pattern 3: FTS5 External Content Table

**What:** La tabla de chunks es el contenido real; FTS5 es un índice virtual que apunta a ella. Los triggers mantienen sincronía automática.

**Why:** FTS5 external content permite hacer upsert en la tabla principal y tener el índice FTS actualizado vía triggers, sin duplicar el texto. [CITED: https://sqlite.org/fts5.html]

```sql
-- Tabla de contenido real (canonical data)
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    kb_id       TEXT NOT NULL,
    source_path TEXT NOT NULL,
    position    INTEGER NOT NULL,
    text        TEXT NOT NULL
);

-- FTS5 external content
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content=chunks,
    content_rowid=rowid,
    tokenize='unicode61'
);

-- Triggers de sincronización
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
```

### Pattern 4: ChromaDB PersistentClient — colección por kb_id (KNOW-11)

**What:** Cada base de conocimiento es una colección separada en ChromaDB. [CITED: https://cookbook.chromadb.dev/core/clients/]

```python
# Source: ChromaDB docs — PersistentClient
import chromadb

client = chromadb.PersistentClient(path=str(data_dir / "chroma"))

# Una colección por BC (kb_id)
collection = client.get_or_create_collection(
    name=kb_id,  # e.g. "personal", "ragcorp", "beca-ciber-1"
    metadata={"hnsw:space": "cosine"}
)

# Upsert con embeddings pre-computados (de OllamaEmbeddingProvider)
collection.upsert(
    ids=[entry.entry_id for entry in entries],
    embeddings=[list(vec) for vec in vectors],
    documents=[entry.chunk.text for entry in entries],
    metadatas=[{
        "source_path": entry.chunk.source_path,
        "position": entry.chunk.position,
        "kb_id": entry.kb_id,
    } for entry in entries],
)
```

**Importante ChromaDB 1.x:** La API `upsert()` admite `embeddings` precomputados — no se necesita que ChromaDB calcule embeddings propios. El `OllamaEmbeddingProvider` genera los vectores y ChromaDB los almacena.

### Pattern 5: Secret Detection — 3 Capas (D-29)

**What:** Las tres capas deben ejecutarse en orden; un match en cualquier capa excluye el archivo entero.

```python
# Source: [ASSUMED] — derivado de D-29 y secrets_patterns.py existente

# Capa 1: path/extension denylist (archivo NI SE ABRE)
PATH_DENYLIST = frozenset({".env", ".env.local", ".env.production", "credentials"})
EXT_DENYLIST = frozenset({".key", ".pem", ".p12", ".pfx", ".ppk"})
FILENAME_PATTERNS = [re.compile(r"^id_rsa"), re.compile(r"^id_ed25519")]

# Capa 2: scan del contenido con BUILTIN_SECRET_PATTERNS (importado de gateway)
from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS

def _scan_content(text: str) -> str | None:
    """Retorna nombre del patrón si hay match, None si limpio."""
    for name, pattern in BUILTIN_SECRET_PATTERNS:
        if pattern.search(text):
            return name
    return None

# Capa 3: Shannon entropy (tokens ≥ 20 chars)
import math

BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS = "0123456789abcdefABCDEF"
BASE64_THRESHOLD = 4.5   # Yelp detect-secrets default [CITED: github.com/Yelp/detect-secrets]
HEX_THRESHOLD = 3.0      # Yelp detect-secrets default

def _shannon_entropy(data: str, charset: str) -> float:
    if not data:
        return 0.0
    entropy = 0.0
    for char in charset:
        p_x = data.count(char) / len(data)
        if p_x > 0:
            entropy -= p_x * math.log2(p_x)
    return entropy

def _has_high_entropy_token(text: str, allowlist_active: bool) -> bool:
    """True si algún token ≥20 chars supera el umbral de entropía."""
    if allowlist_active:
        return False  # D-30: allowlist desactiva SOLO esta capa
    for token in text.split():
        if len(token) < 20:
            continue
        b64_entropy = _shannon_entropy(token, BASE64_CHARS)
        if b64_entropy >= BASE64_THRESHOLD:
            return True
        hex_entropy = _shannon_entropy(token, HEX_CHARS)
        if hex_entropy >= HEX_THRESHOLD:
            return True
    return False
```

**Timing:** La capa 2 requiere texto extraído. El pipeline extrae primero a buffer temporal, escanea, y solo si limpio procede a FTS5/Chroma. El texto del buffer NUNCA persiste si hay match.

### Pattern 6: Rich Progress con fallback no-interactivo (D-35)

```python
# Source: rich.readthedocs.io + [ASSUMED] patrón sys.stdout.isatty()
import sys
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TaskProgressColumn

def make_progress(interactive: bool) -> Progress | None:
    if not interactive:
        return None  # fallback: logging lines en el caller
    return Progress(
        TextColumn("[bold blue]{task.fields[stage]}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.fields[current_file]}"),
        TimeRemainingColumn(),
    )

# En el pipeline
interactive = sys.stdout.isatty()
progress = make_progress(interactive)
```

### Anti-Patterns to Avoid

- **Importar pydantic en `knowledge/`:** Import-linter tiene contrato de independencia entre capas. `knowledge` solo importa de `core/ports` y `core/domain`. Pydantic SOLO en bootstrap. [VERIFIED: pyproject.toml import-linter contracts]
- **Guardar el texto del secreto en la excepción o en AuditEvent:** Solo el `pattern_name` viaja (mismo patrón que D-20 en gateway). Nunca el valor.
- **FTS5 sin external content table:** Si el texto se guarda solo en FTS5 (sin tabla canonical), el upsert incremental se complica y no se puede iterar sobre los chunks para retrieval.
- **Abrir ChromaDB en modo no-persistente:** Usar siempre `PersistentClient(path=...)`, no `EphemeralClient()`.
- **Re-usar la DB de audit o de traces para el state de ingesta:** Las decisiones D-06/D-22 establecen datos de usuario separados. El `index.db` es una tercera DB en `data/`.
- **Iterar texto completo del archivo para entropía:** Tokenizar por whitespace, evaluar tokens ≥20 chars. Evaluar el archivo completo como un solo string produce falsos positivos masivos.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text extraction | Parser PDF propio | pymupdf `fitz.open()` → `page.get_text()` | Maneja encoding, columnas, ligaduras, fuentes embebidas |
| DOCX parsing | ZIP unpack + XML parse directo | python-docx `Document(path).paragraphs` | OOXML es complejo; python-docx maneja revisiones, tablas anidadas |
| MIME detection | Extensión-based mapping | python-magic `magic.from_file(path, mime=True)` | Extensiones mentidas son comunes en 2TB; libmagic lee magic bytes |
| Vector persistence | Serialización JSON de vectores a SQLite | chromadb `PersistentClient` | HNSW indexado, búsqueda cosine, colecciones, metadatos — todo gratis |
| Entropy calculation | Algo propio con umbrales inventados | Implementación Shannon con umbrales de detect-secrets (4.5/3.0) | Umbrales calibrados sobre corpus real de secretos/no-secretos |
| XLSX large file reading | `xlsx` propio | openpyxl `read_only=True` | Archivos grandes consumen GB de RAM sin read_only |

**Key insight:** El dominio más peligroso para reinventar es la extracción de secretos. Los falsos positivos destruyen la experiencia del usuario (archivos legítimos excluidos) y los falsos negativos son brechas de seguridad. Usar los umbrales calibrados industrialmente de Yelp/detect-secrets directamente.

---

## Common Pitfalls

### Pitfall 1: PyMuPDF import name cambia en v1.24+

**What goes wrong:** `import fitz` puede fallar o emitir deprecation warning en pymupdf≥1.24.0.

**Why it happens:** PyMuPDF renombró el módulo en v1.24; `fitz` existe como compat shim pero puede desaparecer.

**How to avoid:** Usar `import pymupdf` como import primario. [CITED: https://pymupdf.readthedocs.io/en/latest/the-basics.html]

```python
try:
    import pymupdf as fitz  # preferido
except ImportError:
    import fitz  # fallback para entornos viejos
```

**Warning signs:** `DeprecationWarning: fitz is deprecated` en logs de test.

### Pitfall 2: PDFs encriptados — `doc.authenticate("")` antes de `page.get_text()`

**What goes wrong:** `doc[0].get_text()` en un PDF protegido retorna vacío o lanza excepción.

**Why it happens:** pymupdf abre el archivo pero no puede leer páginas sin autenticación.

**How to avoid:** Detectar antes de extraer:

```python
doc = pymupdf.open(path)
if doc.is_encrypted:
    # D-40: nunca pedir password
    return None  # → skipped_unsupported
```

**Warning signs:** `text == ""` en PDFs que visualmente tienen contenido.

### Pitfall 3: WAL en NTFS — el mismo que en audit.db y traces.db

**What goes wrong:** `PRAGMA journal_mode=WAL` sobre NTFS/fuseblk no garantiza durabilidad; el state store puede corromperse ante crash.

**Why it happens:** El filesystem NTFS no implementa las garantías POSIX que WAL requiere.

**How to avoid:** Replicar el smoke test fail-fast de `open_gateway_db`:

```python
row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
if row[0].lower() != "wal":
    raise IndexIntegrityError(...)
```

**Warning signs:** `journal_mode` retorna `"delete"` o `"memory"` — el owner tiene ~/Data en NTFS (este proyecto corre con `data_dir` en ext4, pero si el owner mueve `data/` a NTFS el smoke test lo detecta).

### Pitfall 4: Import linter — `knowledge` no puede importar de `gateway`

**What goes wrong:** `from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS` en `knowledge/secret_filter.py` viola el contrato de independencia de capas.

**Why it happens:** `pyproject.toml` tiene un contrato `independence` que lista `gateway` y `knowledge` como módulos independientes.

**How to avoid:** Hay dos opciones válidas — el planner debe elegir una:

1. **Mover `BUILTIN_SECRET_PATTERNS` a `core/`:** Como `core/domain/security.py` ya existe, los patrones podrían vivir en `core/domain/secrets.py` (pero `core` es stdlib-only — `re` es stdlib, OK).
2. **Inyectar los patrones como parámetro:** El composition root en `bootstrap/cli.py` importa de `gateway` (bootstrap no tiene restricción de independence) y pasa los patrones al `SecretFilter` por constructor.

**Recomendación:** Opción 2 (inyección). Bootstrap importa de gateway, pasa `BUILTIN_SECRET_PATTERNS` al `SecretFilter`. Respeta el contrato de independence sin mover código. El CONTEXT.md dice "reuso de BUILTIN_SECRET_PATTERNS de `src/gateway/secrets_patterns.py`" — el reuso puede ser por inyección, no por import directo.

**Warning signs:** `uv run lint-imports` falla con "knowledge imports from gateway".

### Pitfall 5: ChromaDB 1.x — embedding dimension mismatch entre colecciones

**What goes wrong:** Una colección creada con vectores de dimensión 384 no acepta luego vectores de dimensión 768 (si el owner cambia el modelo Ollama).

**Why it happens:** ChromaDB almacena la dimensión al crear la colección; discrepancias causan error en upsert.

**How to avoid:** La dimensión del modelo Ollama actual (`nomic-embed-text`) es 768 dims. Almacenar en metadata de la colección el modelo y la dimensión usados. Ante cambio de modelo: nueva colección o re-indexación completa.

```python
collection = client.get_or_create_collection(
    name=kb_id,
    metadata={
        "hnsw:space": "cosine",
        "embedding_model": settings.embedding_model,
        "embedding_dim": 768,
    }
)
```

### Pitfall 6: Chunking sobre texto vacío — extractores que retornan `""`

**What goes wrong:** El chunker procesa `text=""` y produce un chunk con texto vacío; ese chunk se indexa en FTS5 y en ChromaDB como ruido.

**Why it happens:** Archivos scaneados (PDF de imagen sin OCR), extractores que fallan silenciosamente.

**How to avoid:** Pipeline verifica `extracted_content.text.strip() != ""` antes de chunking. Si vacío: estado `extracted` en SQLite (o `skipped_unsupported` si es PDF sin texto), sin indexar chunks.

### Pitfall 7: shannon entropy — tokens cortados por puntuación

**What goes wrong:** El tokenizador por `split()` no corta `"sk-ant-key123...;"` correctamente; el `;` queda adjunto al token y la entropía baja.

**Why it happens:** Punct characters cambian el conteo de caracteres en charset.

**How to avoid:** Normalizar tokens antes del cálculo de entropía:

```python
import re
_TOKEN_RE = re.compile(r'[A-Za-z0-9+/=_\-]{20,}')
tokens = _TOKEN_RE.findall(text)
```

---

## Code Examples

### Extractor Registration y Resolution

```python
# Source: docs/18-prompt-implementacion.md — Plugin Pattern; [ASSUMED] implementation
# knowledge/extractors/registry.py
from core.ports.knowledge import Extractor

class ExtractorRegistry:
    def __init__(self) -> None:
        self._by_type: dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> None:
        for media_type in extractor.media_types:
            self._by_type[media_type] = extractor

    def resolve(self, media_type: str) -> Extractor | None:
        # Exact match first, then prefix (e.g. "text/" matches "text/plain")
        if media_type in self._by_type:
            return self._by_type[media_type]
        prefix = media_type.split("/")[0] + "/"
        return self._by_type.get(prefix)
```

### PDF Extractor con encrypted detection (D-40)

```python
# Source: pymupdf docs [CITED: pymupdf.readthedocs.io/en/latest/document.html]
# knowledge/extractors/pdf.py
from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    import fitz

from core.domain.knowledge import ExtractedContent, SourceFile

class PdfExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/pdf"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        doc = fitz.open(source.path)
        try:
            if doc.is_encrypted:
                # D-40: nunca pedir password; el caller marca skipped_unsupported
                raise UnsupportedFileError(f"PDF encriptado: {source.path}")
            text = "\n\n".join(page.get_text() for page in doc)
            metadata = {
                "page_count": len(doc),
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
            }
        finally:
            doc.close()
        return ExtractedContent(source=source, text=text, metadata=metadata)
```

### State Store — upsert atómico por archivo

```python
# Source: [ASSUMED] — derivado de patrón open_gateway_db + requisito KNOW-03
def mark_extracted(self, path: str) -> None:
    """Transición atómica: cualquier estado → extracted."""
    self._conn.execute(
        """INSERT INTO file_state (path, kb_id, size, mtime, status, updated_at)
           VALUES (?, ?, ?, ?, 'extracted', unixepoch())
           ON CONFLICT(path) DO UPDATE SET
               status = 'extracted',
               attempts = attempts,
               error = NULL,
               updated_at = unixepoch()
        """,
        (path, ...),
    )
    self._conn.commit()  # commit por archivo — reanudabilidad (KNOW-03)
```

### CLI --estimate sin tocar extractores

```python
# Source: [ASSUMED] — derivado de D-34 y KNOW-08
def estimate(ruta: Path, bc: str, settings: IngestSettings) -> EstimateResult:
    """Recorre file_state y los archivos del filesystem, proyecta sin extraer."""
    pending_files = _collect_pending(ruta, bc)  # scanner rápido (stat only)
    total_bytes = sum(f.size for f in pending_files)
    # Proyección: ~512 tokens/chunk, ~4 chars/token en promedio
    projected_chunks = int(total_bytes / (512 * 4))
    # nomic-embed-text: ~2ms/chunk en CPU local (estimación conservadora)
    embed_seconds = projected_chunks * 0.002
    return EstimateResult(
        files=len(pending_files),
        total_bytes=total_bytes,
        projected_chunks=projected_chunks,
        embed_time_s=embed_seconds,
        cost_usd=0.0,  # D-34: Ollama local, costo $0 explícito
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `import fitz` | `import pymupdf` | pymupdf 1.24.0 | Import name correcto; fitz es compat shim |
| ChromaDB 0.x `.add()` only | ChromaDB 1.x `.upsert()` para idempotencia | ChromaDB 1.0.0 | Upsert permite re-indexación incremental sin duplicados |
| tqdm para progress | Rich Progress (integrado con output panels) | 2024 | Una sola librería para progress + tablas + colores |
| Chunking fixed-size por chars | Chunking por tokens con overlap | 2024-2025 | Mejora retrieval ~15%; chunk boundaries en boundaries de palabras |

**Deprecated/outdated:**
- `PyPDF2`: deprecado, reemplazado por pymupdf y pypdf (distinto). Decisión del owner ya tomada.
- `pdfminer.six`: 30-45x más lento que pymupdf para extracción de texto.
- ChromaDB `.add()` sin upsert: en pipelines incrementales produce `DuplicateIDError`.

---

## Chunking Strategy (D-33 — Claude's Discretion)

**Recomendación del researcher:**

| Tipo de archivo | Chunk size (tokens) | Overlap | Rationale |
|----------------|--------------------|---------|----|
| Texto / Markdown / Código | 512 tokens | 10% (51 tokens) | Benchmark 2026: mejor accuracy promedio [CITED: firecrawl.dev/blog/best-chunking-strategies-rag] |
| PDF (prosa) | 512 tokens | 10% | Igual que texto |
| CSV / XLSX | Por fila o grupo de 10 filas | 0% | Tabular: overlap no aporta |
| Código (PY/JS/TS) | 512 tokens | 10% | Mantener funciones completas si caben |

**Tamaño estimado de token:** ~4 caracteres (aproximación). Para chunk de 512 tokens ≈ 2048 chars.

**Límite de tamaño de archivo (D-41):** Default recomendado = 100 MB. Archivos >100 MB se indexan solo con metadatos (nombre, tipo, tamaño, fecha). Configurable en `[ingest] max_file_bytes`.

**Denylist de directorios (D-42):** `.git`, `node_modules`, `.cache`, `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.tox`, `*.egg-info`.

---

## Entropy Thresholds — Justificación

Los umbrales de Yelp/detect-secrets son los valores calibrados sobre corpus real más citados en la industria:

- **Base64 strings (charset A-Za-z0-9+/=):** threshold = **4.5 bits** — calibrado para cubrir API keys (sk-*, AKIA*, ghp_*) sin excluir texto en prosa (inglés típico: ~4.0-4.2 bits en base64 charset). [CITED: github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/high_entropy_strings.py]
- **Hex strings (charset 0-9a-fA-F):** threshold = **3.0 bits** — hex tiene menor charset; el threshold más bajo captura hashes/tokens hex.
- **Longitud mínima del token:** 20 chars — tokens cortos tienen alta entropía por azar estadístico.

La capa de entropía es desactivable por ruta via `config.toml` allowlist (D-30). La desactivación es opt-in explícito del owner, no default.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | Runtime | ✓ | 3.14.5 | — |
| uv | Dep management | ✓ | 0.11.18 | — |
| SQLite FTS5 | `knowledge/fts_index.py` | ✓ | stdlib sqlite3 | — |
| libmagic.so.1 | python-magic | ✓ | /usr/lib/libmagic.so.1 | — |
| ffprobe | video/audio metadata | ✓ | n8.1.1 (/usr/bin/ffprobe) | — |
| Ollama API | OllamaEmbeddingProvider | ✗ | Not running / not installed | D-32: FTS5 sigue, embeddings quedan en `extracted` para re-run |
| mediainfo CLI | pymediainfo | ✗ | Not found | Usar ffprobe via subprocess (ya disponible) |

**Missing dependencies con fallback:**
- **Ollama:** D-32 cubre explícitamente este caso. El pipeline no aborta. Los archivos quedan `extracted` y un re-run con Ollama activo completa los embeddings. El planner debe incluir instrucciones para instalar Ollama y descargar `nomic-embed-text` (274MB) como tarea Wave 0.
- **mediainfo:** No se instala — se usa ffprobe vía subprocess.

**Missing dependencies sin fallback:**
- Ninguna — todas las dependencias externas tienen fallback o están disponibles.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.x |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/knowledge/ -x -q` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| KNOW-01 | `wyss index <ruta>` escanea e indexa | integration | `uv run pytest tests/knowledge/test_pipeline.py -x` | ❌ Wave 0 |
| KNOW-02 | 10 modificados no re-procesan resto | unit | `uv run pytest tests/knowledge/test_state_store.py::test_incremental_skip -x` | ❌ Wave 0 |
| KNOW-03 | Crash-resume continúa desde el archivo correcto | unit | `uv run pytest tests/knowledge/test_state_store.py::test_crash_resume -x` | ❌ Wave 0 |
| KNOW-06 | Extractor nuevo no modifica pipeline | unit | `uv run pytest tests/knowledge/test_pipeline.py::test_new_extractor_no_pipeline_change -x` | ❌ Wave 0 |
| KNOW-07 | Secreto plantado no aparece en índice | integration (directed) | `uv run pytest tests/knowledge/test_secret_filter.py::test_planted_secret_not_indexed -x` | ❌ Wave 0 |
| KNOW-08 | `--estimate` proyecta sin llamar extractores | unit | `uv run pytest tests/cli/test_index_command.py::test_estimate_no_extraction -x` | ❌ Wave 0 |
| KNOW-09 | Progress visible en interactiva, log en no-interactiva | unit | `uv run pytest tests/cli/test_index_command.py::test_progress_modes -x` | ❌ Wave 0 |
| KNOW-11 | Colección separada por kb_id en ChromaDB | unit | `uv run pytest tests/knowledge/test_vector_index.py::test_separate_collections -x` | ❌ Wave 0 |

### Wave 0 Gaps

- [ ] `tests/knowledge/__init__.py` — paquete de tests
- [ ] `tests/knowledge/conftest.py` — fixtures: `tmp_path` DB, fake BC, fake extractors, sample files
- [ ] `tests/knowledge/test_scanner.py` — cubre KNOW-01 (scan paths, dirs denylist, symlinks)
- [ ] `tests/knowledge/test_secret_filter.py` — cubre KNOW-07 (prueba dirigida obligatoria)
- [ ] `tests/knowledge/test_state_store.py` — cubre KNOW-02 + KNOW-03
- [ ] `tests/knowledge/test_chunker.py` — chunking correcto por tipo
- [ ] `tests/knowledge/test_fts_index.py` — FTS5 upsert + search
- [ ] `tests/knowledge/test_vector_index.py` — ChromaDB colección por kb_id (requiere `chromadb` instalado)
- [ ] `tests/knowledge/test_pipeline.py` — pipeline completo + extensibilidad
- [ ] `tests/knowledge/extractors/` — directorio de tests de extractores
- [ ] `tests/cli/__init__.py` + `tests/cli/test_index_command.py` — CLI command tests

**Nota:** Los tests de `VectorIndex` que usan ChromaDB deben marcarse `@pytest.mark.integration` (requieren disco; `tmp_path` ChromaDB es válido para tests, no necesita Ollama real). Tests de embedding real marcados `@pytest.mark.integration skipif WYSS_TEST_OLLAMA`.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/knowledge/ -x -q`
- **Per wave merge:** `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`
- **Phase gate:** Full suite green antes de `/gsd:verify-work`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (ingesta local, sin auth) |
| V3 Session Management | no | — |
| V4 Access Control | yes | `kb_id` como colección separada; filtro estructural antes de retrieval (regla #3) |
| V5 Input Validation | yes | Extracción como dato no confiable; nunca ejecutar contenido de archivos como instrucción |
| V6 Cryptography | no | SHA-256 solo como fingerprint incremental, no como control de seguridad |
| V8 Data Protection | yes | Secretos excluidos antes de indexar (regla #8); `index.db` sin chmod 0600 propio (datos no sensibles, pero considerar) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secreto en archivo indexado | Information Disclosure | 3-layer secret filter ANTES de indexar (D-27/D-29) |
| Prompt injection via contenido indexado | Tampering | POL-07 (Fase 7): contenido de BC es dato no confiable — pero en Fase 3 el pipeline no pasa contenido a LLM, solo indexa |
| Path traversal en `wyss index <ruta>` | Tampering | `Path.resolve()` antes de `os.walk`; verificar que la ruta es un directorio real |
| Symlink loop (directory) | DoS | D-42: symlinks no se siguen en el scanner |
| Archivo gigante (DoS memoria) | DoS | D-41: límite configurable; archivos grandes → solo metadatos |
| NTFS dirty bit → index.db ro | Tampering | Smoke test WAL fail-fast al abrir `index.db` (mismo patrón que audit.db/traces.db) |

---

## Project Constraints (from CLAUDE.md)

- **Arquitectura hexagonal:** `knowledge/` solo importa de `core/ports/` y `core/domain/`. NUNCA de `gateway/`, `audit/`, `bootstrap/` directamente.
- **Pydantic SOLO en bootstrap:** La sección `[ingest]` del config se agrega a `WyssConfigModel` en `bootstrap/config.py`. Los frozen dataclasses de configuración viven en `core/domain/`.
- **Regla #8 — Secretos fuera del índice:** No hay excepciones. La prueba dirigida (criterio 4) es obligatoria.
- **Regla #9 — Extensibilidad sin ruptura:** El test de extensibilidad (criterio 6) es obligatorio. Agregar un extractor NO modifica una línea del pipeline.
- **Regla #1 — Auditoría obligatoria:** Cada exclusión de secreto genera un AuditEvent (D-28). Archivos `failed` registran el error en SQLite.
- **TDD + cadena verde:** `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` debe pasar antes de cada commit.
- **Import linter independence:** `knowledge` y `gateway` son módulos independientes — los patrones de secretos se inyectan, no se importan directamente (ver Pitfall 4).
- **GSD workflow:** No hacer ediciones directas al repo fuera de un GSD workflow.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | nomic-embed-text produce vectores de 768 dimensiones | Standard Stack / Pitfall 5 | Si el modelo Ollama del owner es diferente, la dimensión de colección ChromaDB será incorrecta. Solución: leer la dimensión del primer batch de embeddings y guardarla en metadata de colección |
| A2 | El threshold de entropía base64≥4.5/hex≥3.0 es adecuado para el corpus del owner | Secret Detection | Falsos positivos (archivos legítimos excluidos) o falsos negativos (secretos que pasan). La allowlist (D-30) mitiga falsos positivos; el threshold puede ajustarse en config |
| A3 | 512 tokens con 10% overlap como default de chunking es adecuado | Chunking Strategy | Si el retrieval en Fase 4 muestra baja precisión, el chunking puede ajustarse vía config sin re-arquitectura |
| A4 | Default límite de tamaño = 100 MB es razonable para 2TB | Chunking Strategy | Si el owner tiene muchos archivos >100MB que quiere indexar completamente, el default debe subir |
| A5 | `mediainfo` CLI no está instalado; ffprobe es el substituto correcto para metadatos de video | Environment | Si pymediainfo es preferido, instalar `mediainfo` vía pacman |
| A6 | La inyección de BUILTIN_SECRET_PATTERNS desde bootstrap satisface el requisito de "reuso" de D-29 sin violar import-linter | Pitfall 4 | Si el planner prefiere mover los patrones a `core/domain/`, es también válido (re` es stdlib-only) |

**Si esta tabla está vacía:** Todos los claims en este research fueron verificados o citados — ninguna confirmación de usuario necesaria.

---

## Open Questions

1. **¿Dónde vive la CLI entry point?**
   - Lo que sabemos: La spec canónica dice `bootstrap/` es el composition root. El CLAUDE.md menciona `bootstrap/cli.py` como ubicación implícita.
   - Lo que no está claro: `pyproject.toml` necesita un `[project.scripts]` entry point como `wyss = "bootstrap.cli:app"`. El planner debe agregarlo.
   - Recomendación: El planner agrega `wyss = "bootstrap.cli:app"` a `[project.scripts]` en `pyproject.toml`. Typer `app` es el objeto Typer de nivel raíz.

2. **¿`--bc` tiene default o es obligatorio?**
   - Lo que sabemos: D-42 dice "cómo se nombra la BC es Claude's Discretion respetando KNOW-11".
   - Lo que no está claro: Si el owner no especifica BC, ¿usa un default como `"default"` o falla con error?
   - Recomendación: Default `"default"` si no se especifica — el owner puede renombrarlo en config. Siempre muestra el kb_id usado en el output.

3. **¿Cómo se maneja `wyss index` sobre una ruta ya indexada con un kb_id diferente?**
   - Lo que sabemos: `file_state` tiene un `kb_id` por archivo. Si el mismo archivo se indexa con otro `kb_id`, debería aparecer en ambas colecciones.
   - Lo que no está claro: Si se re-run con diferente `--bc`, ¿el archivo se agrega a ambas BCs o se reemplaza?
   - Recomendación: `(path, kb_id)` como primary key compuesta en `file_state`. Cada par es independiente.

---

## Sources

### Primary (HIGH confidence)
- `src/gateway/secrets_patterns.py` — patrones built-in verificados en codebase
- `src/core/ports/knowledge.py` — contratos de ports verificados en codebase
- `src/gateway/providers/ollama.py` — OllamaEmbeddingProvider verificado en codebase
- `docs/18-prompt-implementacion.md` — spec canónica del owner verificada
- `.planning/phases/03-pipeline-de-ingesta/03-CONTEXT.md` — decisiones verificadas
- `pyproject.toml` — dependencias actuales y import-linter contracts verificados
- [CITED: https://sqlite.org/fts5.html] — FTS5 external content tables
- [CITED: https://github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/high_entropy_strings.py] — entropy thresholds
- [CITED: https://pymupdf.readthedocs.io/en/latest/document.html] — PyMuPDF encrypted detection

### Secondary (MEDIUM confidence)
- [CITED: https://cookbook.chromadb.dev/core/clients/] — ChromaDB PersistentClient API
- [CITED: https://rich.readthedocs.io/en/latest/progress.html] — Rich Progress columns
- [CITED: https://www.firecrawl.dev/blog/best-chunking-strategies-rag] — chunking benchmarks 2026

### Tertiary (LOW confidence — marcados [ASSUMED])
- Implementación concreta de ExtractorRegistry — ningún código existente; derivado del spec
- Esquema concreto de `file_state` — derivado de requisitos, no de código existente
- Default 100MB para límite de tamaño — estimación razonable para 2TB, sin benchmark del owner

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — todos los packages verificados en PyPI + slopcheck OK
- Architecture: HIGH — ports existentes + spec canónica + decisions lockeadas
- Secret detection: HIGH — código existente (BUILTIN_SECRET_PATTERNS) + thresholds citados
- Pitfalls: HIGH — verificados contra código existente (import-linter contracts, WAL pattern)
- Chunking defaults: MEDIUM — benchmarks citados pero no validados con corpus del owner

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (30 días — stack estable excepto ChromaDB que evoluciona rápido)
