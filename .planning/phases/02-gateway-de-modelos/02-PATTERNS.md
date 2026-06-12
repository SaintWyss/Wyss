# Phase 2: Gateway de Modelos - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 18 (12 nuevos `src/`, 1 extensión dominio, 1 extensión config, ~7 nuevos `tests/`)
**Analogs found:** 17 / 18 (1 sin analog directo: minimizer fail-closed)

> Esta fase **rellena stubs vacíos** (`src/gateway/__init__.py` = 2 líneas). Casi todo el código nuevo tiene un analog fuerte de Fase 1. El único código verdaderamente nuevo y delicado es el **ContextMinimizer fail-closed** (combina el patrón aditivo de `builtin_deny.py` con regex de secretos sin analog 1:1).

---

## File Classification

| Archivo nuevo/modificado | Role | Data Flow | Analog más cercano | Match |
|---|---|---|---|---|
| `src/core/domain/gateway.py` (MOD: +tier, +purpose en `AgentModelRequest`) | model | — | mismo archivo (extensión aditiva) | exact |
| `src/gateway/providers/anthropic.py` | adapter (driven) | request-response (HTTP) | *RESEARCH Pattern 1* (sin analog HTTP en repo) | research-only |
| `src/gateway/providers/litellm.py` | adapter (driven) | request-response (HTTP) | *RESEARCH Pattern 1* | research-only |
| `src/gateway/providers/ollama.py` | adapter (driven) | request-response (HTTP, batch) | `core/ports/knowledge.py::EmbeddingProvider` (contrato) | contract-match |
| `src/gateway/providers/fakes.py` | test-double | request-response | `tests/ports/fakes.py::FakeModelProvider/FakeEmbeddingProvider` | exact |
| `src/gateway/router.py` | service (application) | transform (puro, determinístico) | `src/core/policy/engine.py` | role-match |
| `src/gateway/minimizer.py` | service (application) | transform (scan fail-closed) | `src/core/policy/engine.py` + `builtin_deny.py` | role-match |
| `src/gateway/secrets_patterns.py` | config (built-in `Final`) | — | `src/core/policy/builtin_deny.py` | exact |
| `src/gateway/cost.py` | service (application) + persistence | CRUD (gasto) + transform (gate) | `src/core/policy/engine.py` (gate) + `src/audit/sqlite_logger.py` (estado) | role-match |
| `src/gateway/traces.py` | adapter (driven, persistence) | CRUD / write-mostly | `src/audit/sqlite_logger.py` | exact |
| `src/gateway/traces_schema.py` | config (DDL) | — | `src/audit/schema.py` | exact |
| `src/gateway/gateway.py` | service (facade) | orquestación (request-response) | `core/ports/gateway.py::ModelGatewayPort` (contrato) + `engine.py` (orquestación pura) | contract-match |
| `src/gateway/__init__.py` (MOD: stub→exports) | barrel | — | `src/audit/__init__.py` | exact |
| `src/bootstrap/config.py` (MOD: +sección `[gateway]`) | config (bootstrap) | transform (Pydantic→dominio) | mismo archivo (patrón `PolicyConfigModel`) | exact |
| `tests/gateway/conftest.py` | test | — | `tests/audit/conftest.py` + `tests/policy/conftest.py` | exact |
| `tests/gateway/test_minimizer.py` | test (security) | — | `tests/policy/test_golden_plans.py` (estilo golden/security) | role-match |
| `tests/gateway/test_cost_gate.py` | test (security) | — | `tests/policy/test_golden_plans.py` | role-match |
| `tests/gateway/test_traces.py` | test (integration) | — | `tests/audit/test_sqlite_logger.py` | exact |

---

## Pattern Assignments

### `src/core/domain/gateway.py` (MOD — extensión frozen aditiva)

**Analog:** mismo archivo, `src/core/domain/gateway.py` líneas 26-30.

D-26 exige `tier` + `purpose` en `AgentModelRequest`. Es un frozen dataclass consumido por `tests/ports/fakes.py` (línea 139, `FakeModelGatewayPort`) y `tests/ports/test_conformance.py`. **Agregar campos con default** para no romper construcciones existentes (Pitfall 5). Patrón frozen actual:

```python
@dataclass(frozen=True, slots=True)
class AgentModelRequest:
    """Pedido de un agente al gateway (routing/minimizado/costo ocurren adentro)."""
    agent_id: str
    task_id: str
    prompt: str
    # NUEVO (D-26) — defaults para no romper tests Fase 1:
    tier: str = "economico"
    purpose: str = "general"
```

`ModelRequest` (líneas 6-13) y `ModelResponse` (15-23) **NO se tocan** — ya tienen todo lo necesario (`model_alias`, `max_tokens`, `tokens_in/out`, `cost_usd`, `latency_ms`). Actualizar en el mismo task los fakes/conformance y correr `uv run mypy && uv run pytest tests/ports`.

---

### `src/gateway/secrets_patterns.py` (config, built-in `Final`)

**Analog:** `src/core/policy/builtin_deny.py` (exact). Replicar EXACTO la estructura `Final[tuple[...]]` no-vaciable por config.

**Imports + docstring pattern** (`builtin_deny.py` líneas 1-20):
```python
"""Patrones de secreto built-in: NO removibles por config (D-21, regla #4/#8).

`BUILTIN_SECRET_PATTERNS` es `Final` — la config TOML solo puede AGREGAR patrones
(`patterns = BUILTIN_SECRET_PATTERNS + tuple(config_patterns)`), nunca vaciar estos.
Solo stdlib (`re`, `typing.Final`). NO vive en `core/` (regex de adapter) — vive en `gateway/`.
"""
from typing import Final
import re
```

**Estructura `Final` aditiva** (espejo de `BUILTIN_DENY` líneas 20-64; contenido exacto en RESEARCH Pattern 2):
```python
BUILTIN_SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key",    re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_access",    re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat",    re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_fine",   re.compile(r"github_pat_[A-Za-z0-9_]{50,}")),
    ("jwt",           re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("pem_private",   re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("slack_token",   re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
)
```
**Lección de `builtin_deny.py`:** la razón de ser `Final` está documentada en su docstring ("si la config pudiera removerlas, el nivel D dejaría de ser absoluto editando un archivo"). Copiar esa justificación al docstring del minimizer.

---

### `src/gateway/minimizer.py` (service, scan fail-closed) — código nuevo delicado

**Analog parcial:** `src/core/policy/engine.py` (clase pura inyectada con reglas) + patrón aditivo de `config.py` línea 92 (`deny = BUILTIN_DENY + config_deny`). **Sin analog 1:1** del scan de secretos — es el código nuevo de mayor foco de tests.

**Patrón "clase pura, reglas inyectadas por constructor"** (de `engine.py` líneas 34-39):
```python
class CognitivePolicyEngine:
    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules
```
→ El minimizer sigue esa forma: `ContextMinimizer(env_values, config_patterns)`, combina `BUILTIN_SECRET_PATTERNS + config_patterns` (aditivo, como `config.py:92`), método `scan(prompt) -> str` puro. Implementación completa en RESEARCH Pattern 2.

**Excepción de dominio** (deriva de `WyssError` en `core/domain/errors.py` líneas 4-22 — mismo patrón que `PolicyViolation`, `AuditIntegrityError`):
```python
# Agregar a core/domain/errors.py (es donde viven las excepciones del sistema):
class SecretDetected(WyssError):
    """Payload bloqueado: matcheó un patrón de secreto. NUNCA recibe el valor (D-20)."""
    def __init__(self, pattern_name: str) -> None:
        super().__init__(f"payload bloqueado: matcheó patrón de secreto '{pattern_name}'")
        self.pattern_name = pattern_name   # nombre del patrón, JAMÁS el secreto
```
**Crítico (D-20):** fail-closed — la llamada NO sale; el error lleva el NOMBRE del patrón, nunca el valor.

---

### `src/gateway/router.py` (service, transform determinístico)

**Analog:** `src/core/policy/engine.py` (role-match: motor puro determinístico, sin IO, sin LLM).

**Patrón "frozen config dataclass + dict lookup fail-fast"** (de `engine.py`; estructura `TierConfig` en RESEARCH Code Examples):
```python
@dataclass(frozen=True, slots=True)   # mismo estilo que todo core.domain
class TierConfig:
    provider: str        # "litellm" | "anthropic"
    model_alias: str
    max_tokens: int

class ModelRouter:
    def __init__(self, tiers: dict[str, TierConfig]) -> None:
        self._tiers = tiers   # reglas inyectadas, como engine._rules

    def resolve(self, tier: str) -> TierConfig:
        try:
            return self._tiers[tier]
        except KeyError:
            raise UnknownTier(tier, available=tuple(self._tiers))  # error claro, auditado (D-17)
```
**Lección de `engine.py`:** fail-closed por diseño — `_base_level` (línea 77-79) devuelve C (no A) ante un type desconocido. El router replica: tier inexistente → error explícito con tiers disponibles, NUNCA fallback silencioso (D-17). `UnknownTier` deriva de `WyssError`.

---

### `src/gateway/cost.py` (service gate + persistence)

**Analog doble:** `src/core/policy/engine.py` (lógica de gate/veto pura) + `src/audit/sqlite_logger.py` (estado durable SQLite). Implementación de `authorize()`/`record()` en RESEARCH Pattern 3.

**Patrón gate ANTES-de-actuar:** el engine veta vía `outcome_for(RiskLevel.D)`; el CostTracker veta vía `BudgetExceeded` ANTES de `provider.complete()` (Pitfall 2 — sin esto el presupuesto es advisory, no enforced).

**Patrón estado SQLite** (de `sqlite_logger.py` — ver `traces.py` abajo; misma conexión/PRAGMAs). El estado de gasto mensual vive en una tabla dentro de `traces.db` (Open Question 3, recomendación: una sola DB de gateway).

**Excepción:**
```python
class BudgetExceeded(WyssError):   # core/domain/errors.py, junto a PolicyViolation
    """Presupuesto (global o por-agente) agotado: la llamada se veta pre-autorización (D-18)."""
```
**Crítico (D-24):** costo SIEMPRE calculado local (`tokens × precio_de_config`); el `response_cost` del provider solo se guarda comparativo, NUNCA gobierna el gate.

---

### `src/gateway/traces.py` (adapter persistence) + `src/gateway/traces_schema.py` (DDL)

**Analog:** `src/audit/sqlite_logger.py` + `src/audit/schema.py` (exact). `traces.db` replica el patrón SQLite probado, pero **es DB separada** (D-22) — y a diferencia de audit, **NO es append-only** (traces expiran a 90 días).

**Patrón conexión + WAL fail-fast smoke test** (`sqlite_logger.py` líneas 35-58 — replicar EXACTO, Pitfall 6 NTFS):
```python
def __init__(self, db_path: Path) -> None:
    self._db_path = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(db_path)
    journal_mode: str | None = None
    for pragma in PRAGMAS:
        row = self._conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        self._conn.close()
        raise AuditIntegrityError(   # o un TraceIntegrityError análogo
            f"traces en {db_path}: journal_mode={journal_mode!r}, se esperaba 'wal'. "
            "Mové data/ a ext4."
        )
    apply_schema(self._conn)
```

**Patrón INSERT parametrizado + commit por evento** (`sqlite_logger.py` líneas 21-25, 60-79):
```python
_INSERT = (
    "INSERT INTO traces (trace_id, task_id, agent_id, tier, purpose, "
    "prompt, output, tokens_in, tokens_out, cost_usd, latency_ms, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
# self._conn.execute(_INSERT, (...)); self._conn.commit()  — nunca interpolar strings
```

**DDL pattern** (`schema.py` — PRAGMAS líneas 13-17, CREATE_TABLE/INDEXES líneas 19-56). **Copiar PRAGMAS y `apply_schema()` tal cual; cambiar la tabla y los índices** por `task_id`/`purpose` (consultabilidad D-22). **OMITIR los triggers append-only** (`schema.py` líneas 40-45) — traces se purgan por retención, audit no:
```python
PRAGMAS: tuple[str, ...] = (              # ← copiar idéntico de schema.py:13-17
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS traces (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT NOT NULL UNIQUE,
  task_id     TEXT, agent_id TEXT, tier TEXT, purpose TEXT,
  prompt      TEXT NOT NULL,   -- POST-minimizer (D-22)
  output      TEXT NOT NULL,
  tokens_in   INTEGER NOT NULL, tokens_out INTEGER NOT NULL,
  cost_usd    REAL NOT NULL, latency_ms INTEGER NOT NULL,
  created_at  TEXT NOT NULL
)
"""
CREATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_traces_task ON traces(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_traces_purpose_time ON traces(purpose, created_at)",
)
# SIN CREATE_TRIGGERS — traces NO es append-only (retención 90d).
```

---

### `src/gateway/gateway.py` (facade `ModelGatewayPort`)

**Analog:** `core/ports/gateway.py::ModelGatewayPort` (contrato a implementar, líneas 17-20) + `engine.py` (orquestación de pasos determinística). Orquesta los 7 pasos de RESEARCH (router → minimizer → cost.authorize → provider.complete con retry → cost.record → traces.write → audit.log).

**Patrón AuditPort inyectado por constructor** (NUNCA `import audit` — Pitfall 4 import-linter `independence`). El gateway depende del Protocol `AuditPort` (`core/ports/audit.py` líneas 9-16):
```python
from core.ports.audit import AuditPort   # puerto en core — OK
# NUNCA: from audit import SqliteAuditLogger   # ← rompe contrato independence
```
Emite eventos con `AuditEvent.new(...)` usando `AuditEventType.COST_RECORDED` (ya existe, `domain/audit.py:32`) para el record de costo, y un tipo nuevo o `TASK_FAILED` para veto/secreto. **El audit registra NOMBRE del patrón / motivo, nunca el secreto** (D-20, V7).

**Patrón retry manual centralizado** (sin analog en repo — RESEARCH Don't Hand-Roll): el retry vive en `ask()`, no en los providers; cada retry RE-LLAMA `cost.authorize()` (D-25). 4xx → fail-fast; timeout/429/5xx → 2x backoff mismo provider.

---

### `src/gateway/providers/*.py` (adapters HTTP)

**Analog:** ninguno en repo (no hay adapter HTTP aún) → usar **RESEARCH Pattern 1** (anthropic.py, litellm.py) y **Code Examples** (ollama.py) literalmente. El contrato lo da `core/ports/gateway.py::ModelProvider` (líneas 8-14: `@property name`, `async def complete`) y `EmbeddingProvider` (`core/ports/knowledge.py` líneas 33-36: `async def embed(texts) -> Sequence[Vector]` — REUSAR este port, no inventar uno).

**Regla arquitectónica (STACK + import-linter `core puro`):** `httpx` y los dicts de respuesta JSON viven SOLO acá; afuera solo viaja `ModelResponse`/`Vector` de dominio. `core/` es stdlib-only (pyproject `forbidden_modules` incluye `pydantic` y todas las capas).

**`fakes.py`:** reusar / espejar `tests/ports/fakes.py::FakeModelProvider` (líneas 130-137) y `FakeEmbeddingProvider` (líneas 93-95) — ya implementan la firma exacta del port.

---

### `src/gateway/__init__.py` (barrel) + `src/bootstrap/config.py` (MOD)

**`__init__.py` analog:** `src/audit/__init__.py` (exact) — docstring + `from gateway.gateway import ModelGateway` + `__all__`.

**config.py analog:** mismo archivo, sección `[policy]` (`PolicyConfigModel` líneas 53-63, mapeo `_to_settings` 87-107). Agregar `GatewayConfigModel(BaseModel)` con `model_config = ConfigDict(extra="forbid")` (fail-closed, líneas 45/56/69) para tiers/precios/presupuesto/timeout/retención, y un mapper `_to_gateway_settings` que muere en frozen dataclasses de dominio (Pydantic NUNCA entra a `gateway/`). **Patrón aditivo** para `config_patterns` del minimizer = espejo de `deny = BUILTIN_DENY + config_deny` (línea 92).

---

## Shared Patterns

### Excepciones de dominio (fail-closed)
**Source:** `src/core/domain/errors.py` líneas 4-22 — todas derivan de `WyssError`.
**Apply to:** `SecretDetected`, `BudgetExceeded`, `UnknownTier` (agregarlas acá, junto a `PolicyViolation`/`AuditIntegrityError`/`ConfigError`).
```python
class WyssError(Exception):
    """Raíz de todos los errores del sistema."""
class PolicyViolation(WyssError): ...   # patrón a imitar
```

### Built-in `Final` + config aditiva (no vaciable)
**Source:** `src/core/policy/builtin_deny.py` (`BUILTIN_DENY: Final[tuple[...]]`) + `src/bootstrap/config.py:92` (`BUILTIN_DENY + config_deny`).
**Apply to:** `secrets_patterns.py` (`BUILTIN_SECRET_PATTERNS`) y el merge en el minimizer. La seguridad vive en código como `Final`; config solo AGREGA.

### Persistencia SQLite (WAL fail-fast)
**Source:** `src/audit/sqlite_logger.py` líneas 35-58 (smoke test WAL) + `src/audit/schema.py` líneas 13-55 (PRAGMAS + `apply_schema` idempotente).
**Apply to:** `traces.py` + `traces_schema.py` y la tabla de estado de gasto de `cost.py`. Replicar PRAGMAS y el fail-fast EXACTO (Pitfall 6 NTFS). **Diferencia clave:** OMITIR triggers append-only (traces expiran).

### AuditPort inyectado, nunca importado
**Source:** `src/core/ports/audit.py` líneas 9-16 (Protocol) + `tests/ports/fakes.py::FakeAuditPort` líneas 42-62.
**Apply to:** `gateway.py`, `cost.py`. DI por constructor (`audit: AuditPort`); el `SqliteAuditLogger` concreto lo cablea bootstrap. `import audit` en `gateway/` rompe el contrato import-linter `independence` (Pitfall 4).

### Frontera Pydantic→dominio (solo en bootstrap)
**Source:** `src/bootstrap/config.py` — `WyssConfigModel`/`PolicyConfigModel` (`extra="forbid"`), `_to_settings` (Pydantic muere acá), `load_settings` con `ConfigError` legible.
**Apply to:** validación de `[gateway]`. Pydantic NUNCA cruza a `gateway/` ni `core/`.

### Fixtures de test
**Source:** `tests/audit/conftest.py` (fixture `tmp_path → DB`, factory `make_event`) + `tests/policy/conftest.py` (fixtures `engine`/`engine_sin_config` con reglas inyectadas).
**Apply to:** `tests/gateway/conftest.py` — fixtures: `respx`-mocked `AsyncClient`, `FakeAuditPort` (reusar de `tests/ports/fakes.py`), `tmp_path` para `traces.db`, factory de `AgentModelRequest`.

---

## No Analog Found

| Archivo | Role | Data Flow | Razón |
|---|---|---|---|
| `src/gateway/minimizer.py` (scan de secretos) | service | transform | No existe detección de secretos en el repo. La **forma** (clase pura inyectada + aditivo) viene de `engine.py`/`config.py`, pero el regex-scan es código nuevo. Foco de tests de seguridad (GATE-03). Usar RESEARCH Pattern 2. |
| `src/gateway/providers/{anthropic,litellm,ollama}.py` | adapter | HTTP request-response | No hay adapter HTTP en el repo. Usar RESEARCH Pattern 1 + Code Examples (httpx directo, verificados contra docs oficiales). El contrato (`ModelProvider`/`EmbeddingProvider`) sí existe. |
| `src/gateway/gateway.py` retry manual | service | — | El backoff/retry centralizado que re-pasa el gate (D-25) no tiene analog. ~25 líneas, RESEARCH Don't Hand-Roll. |

---

## Metadata

**Analog search scope:** `src/audit/`, `src/core/policy/`, `src/core/ports/`, `src/core/domain/`, `src/bootstrap/`, `tests/ports/`, `tests/policy/`, `tests/audit/`, `pyproject.toml` (contratos import-linter).
**Files scanned:** 13 leídos en profundidad; ~37 fuentes + 19 tests inventariados.
**Import-linter constraints verificados:** `core es puro: stdlib only` (forbidden: pydantic + todas las capas) y `independence` (gateway NO importa audit) — pyproject líneas 60-86.
**Pattern extraction date:** 2026-06-11
