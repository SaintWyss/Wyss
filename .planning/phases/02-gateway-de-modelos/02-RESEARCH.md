# Phase 2: Gateway de Modelos - Research

**Researched:** 2026-06-11
**Domain:** Adaptadores de proveedores LLM async (HTTP), routing por tier, minimización de secretos (fail-closed), gate de presupuesto pre-autorización, tracing SQLite — todo dentro de la arquitectura hexagonal de Wyss.
**Confidence:** HIGH (contratos de código verificados en repo; APIs de proveedores verificadas contra docs oficiales; versiones de libs `[ASSUMED]` por sandbox sin red a registries)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-14..D-26 — investigar CÓMO, no relitigar)

- **D-14 (Proveedores):** Dos `ModelProvider` reales — **LiteLLMProvider** (tier económico, proxy local OpenAI-compatible en `localhost:4000`, ya corriendo en Docker del owner) + **AnthropicProvider** (tier fuerte, API directa). Intercambiables por config sin tocar código. `FakeProvider` para tests.
- **D-15 (Embeddings):** `EmbeddingProvider` real = **Ollama local** (p.ej. nomic-embed-text). Contenido personal nunca sale de la máquina. Fake de embeddings para tests.
- **D-16 (Routing):** Tiers en `config.toml` (`economico` → LiteLLM/modelo X, `fuerte` → Anthropic/modelo Y) con aliases. **El caller declara el tier**; el router resuelve tier→provider+modelo determinísticamente. Sin clasificación automática, sin LLM decidiendo routing.
- **D-17 (Fail-fast):** Si el provider del tier falla → error claro al caller, auditado. **Sin fallback automático de tier, sin retry cross-provider.**
- **D-18 (Presupuesto):** Global mensual + límite opcional por agente, ambos en `config.toml`. CostTracker chequea ambos **ANTES** de cada llamada (pre-autorización). Prepara AGENT-02 (Fase 7).
- **D-19 (Destrabe):** Presupuesto agotado se destraba **solo editando `config.toml` + reload**. Sin override por chat ni comando de agente (regla #6).
- **D-20 (Minimizer fail-closed):** Secreto en payload saliente → **la llamada NO sale** (bloqueo, no redacción). Error auditado registrando QUÉ patrón matchó, **sin loguear el secreto**.
- **D-21 (Tres fuentes de detección):** valores reales del `.env` cargados al boot (match exacto/substring) + regex built-in (sk-, sk-ant-, AKIA, ghp-, JWT, PEM private keys…) + patrones extra por config (aditivos, como la denylist de política).
- **D-22 (Tracing):** DB SQLite **propia y separada** (`traces.db`), distinta de `audit.db` y de datos de usuario. Prompt y output **completos POST-minimizer**, tokens in/out, costo, latencia, task_id, agent_id, tier, purpose. Retención configurable, default **90 días** (audit es forever; traces expiran).
- **D-23 (Sin streaming):** `ask()` devuelve respuesta completa. `ask_stream()` se difiere a Fase 5 si la CLI lo necesita (extensión aditiva).
- **D-24 (Costo):** Tabla local de precios por modelo en `config.toml` (tokens × precio). Cálculo determinístico para todo provider; el gate **nunca** depende de que el provider reporte bien. Si LiteLLM devuelve costo, se guarda en el trace como dato comparativo.
- **D-25 (Retries):** **2 retries con backoff SOLO en transientes** (timeout, 429, 5xx) del MISMO provider; 4xx → fail-fast. Timeout por llamada configurable (default 120s). Cada retry re-pasa el gate de presupuesto.
- **D-26 (Identidad):** `AgentModelRequest` viaja con **agent_id + task_id + tier + purpose** (string corto: "plan", "summarize", "classify"…). Correlación de cadenas vía task_id (sin trace jerárquico por ahora).

### Claude's Discretion

- Esquema exacto de tablas de `traces.db` (respetando campos de D-22).
- Naming de aliases de tiers/modelos en config y estructura interna del módulo `gateway/`.
- Set inicial exacto de regex built-in de secretos (D-21 lista los formatos mínimos).
- Mecánica del "secreto trampa" fixture para el test de GATE-03 (success criterion 2).
- Librería HTTP/SDK por provider (httpx directo vs SDK oficial `anthropic`) — decidir en research según lo que minimice deps. **→ Resuelto abajo: httpx directo (ver "Don't Hand-Roll" y "Decisión de cliente HTTP").**

### Deferred Ideas (OUT OF SCOPE)

- `ask_stream()` streaming — Fase 5 si la CLI lo necesita.
- Trace jerárquico (parent_trace_id / span estilo OpenTelemetry) — Fase 9.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **GATE-01** | Único punto de salida a IA externa; ≥2 proveedores configurables, intercambiables vía config sin tocar código | `ModelProvider` Protocol ya existe en `core/ports/gateway.py`. LiteLLMProvider + AnthropicProvider + FakeProvider en `src/gateway/providers/`. Selección por alias en config (Pattern 3, registry). Verificado: LiteLLM real expone gemini/deepseek/qwen en `localhost:4000`. |
| **GATE-02** | Selección de modelo (lógica local → económico → fuerte) | D-16: caller declara tier; ModelRouter resuelve tier→(provider, model_alias) desde `config.toml`. Determinístico, sin LLM. Mapa de responsabilidad: routing = Application layer (`gateway/`). |
| **GATE-03** | Context Minimizer filtra secretos antes de TODA llamada externa | D-20/D-21: 3 fuentes (env values + regex built-in + config patterns), fail-closed. Regex verificados abajo; pitfall de falsos positivos documentado. Fixture "secreto trampa". |
| **GATE-04** | Cost Tracker registra tokens y costo; actúa como gate (hard-stop, no reporte) | D-18/D-24: tabla precios en config, cálculo determinístico, chequeo pre-autorización contra presupuesto global+agente en `traces.db` (o tabla propia). Pitfall "advisory vs enforced" (PITFALLS Área 6). |
| **GATE-05** | Tracing por llamada: prompt, contexto, output, latencia, costo — consultable, separado de auditoría | D-22: `traces.db` SQLite separada, schema propio, retención 90d. Patrón replicado de `src/audit/sqlite_logger.py` (WAL fail-fast, PRAGMAs). |
</phase_requirements>

## Summary

Esta fase implementa el `gateway/` (capa Application del hexágono) que ya tiene sus puertos definidos en Fase 1 (`core/ports/gateway.py`: `ModelProvider.complete`, `ModelGatewayPort.ask`; `core/domain/gateway.py`: `ModelRequest`, `ModelResponse`, `AgentModelRequest`). El trabajo es **rellenar los stubs** de `src/gateway/__init__.py` con: dos adaptadores de provider reales + uno fake, un `ContextMinimizer` fail-closed, un `CostTracker` que veta antes de llamar, un `ModelRouter` que resuelve tier→provider determinísticamente, y un store de traces SQLite separado. El composition root (`src/bootstrap/`) cablea todo con `AuditPort` inyectado.

Tres restricciones arquitectónicas dominan el diseño y deben respetarse al planificar: (1) **`core/` es stdlib-only** — los SDKs y httpx viven SOLO en `src/gateway/`, jamás en `core/` (import-linter lo refuerza con `include_external_packages=true`); (2) el contrato import-linter de **independencia entre capas** prohíbe que `gateway` importe el paquete `audit` — el gateway depende solo del **puerto** `AuditPort` (que vive en `core/ports`), y el `SqliteAuditLogger` concreto se inyecta desde bootstrap; (3) **Pydantic solo en bootstrap** — los bloques `[gateway]` de config se validan en `src/bootstrap/config.py` y se mapean a frozen dataclasses de dominio antes de entrar al gateway.

**Primary recommendation:** Usar **httpx.AsyncClient directo** (no los SDKs `anthropic`/`openai`) para ambos providers reales. Razón decisiva verificada: los SDKs oficiales reintentan internamente en 429/5xx (típicamente 2 retries con backoff) — envolverlos en la lógica de retry de D-25 produce **doble retry** y descontrol del gate de presupuesto (cada retry debe re-pasar el gate). httpx da control total del retry, un solo cliente para ambos endpoints (LiteLLM es OpenAI-compatible, Anthropic es Messages API — solo cambian headers/shape), menos deps, y conformidad natural con el patrón hexagonal. Implementar el retry/backoff a mano (≤30 líneas) o con `tenacity` (lib liviana) — manual es preferible porque cada retry tiene que re-invocar el gate de presupuesto, lo que no encaja limpio en un decorador.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Resolución tier→provider+modelo (routing) | Application (`gateway/ModelRouter`) | — | Pura lógica de negocio sobre config; determinística (D-16). |
| Llamada HTTP al modelo externo | Driven Adapter (`gateway/providers/*`) | — | Cruza frontera de red; los SDKs/httpx viven acá, nunca en core. |
| Detección/bloqueo de secretos | Application (`gateway/ContextMinimizer`) | — | Spine de seguridad — NO pluggable (ARCHITECTURE: "hard-code the spine"). |
| Gate de presupuesto (veto pre-llamada) | Application (`gateway/CostTracker`) | Persistence (estado de gasto en SQLite) | Decisión de negocio (veta) + estado durable. |
| Persistencia de traces | Driven Adapter (`gateway/traces` SQLite sink) | — | Replica patrón de `audit/sqlite_logger.py`; IO. |
| Cálculo de costo (tokens × precio) | Application (`gateway/CostTracker`) | — | Determinístico, independiente del provider (D-24). |
| Embeddings locales | Driven Adapter (`gateway/providers/ollama`) | — | Cruza frontera HTTP a Ollama local. |
| Validación de config `[gateway]` | Bootstrap (`bootstrap/config.py`) | — | Único lugar con Pydantic; mapea a dominio frozen. |
| Cableado (config→providers→minimizer→cost→router) | Bootstrap (composition root) | — | Único módulo que importa adapters + application juntos. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | `>=0.28` `[ASSUMED]` | Cliente HTTP async para LiteLLM (OpenAI-compatible) y Anthropic (Messages API) y Ollama (embeddings) | Async first-class; un cliente para los tres endpoints; control total del retry (clave para D-25); ya es el patrón asumido en STACK.md (mocks con `respx`). |
| `sqlite3` (stdlib) | — | `traces.db` y estado de presupuesto | Cero deps; replica el patrón ya probado de `audit/sqlite_logger.py` (WAL, PRAGMAs, fail-fast). |
| `tomllib` (stdlib) | — | Lectura de config | Ya en uso en `bootstrap/config.py`. |
| `pydantic` | `>=2.13` (ya en pyproject) | Validación de los bloques `[gateway]` SOLO en bootstrap | Patrón establecido `extra="forbid"`, fail-closed. NUNCA entra a `gateway/` ni `core/`. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tenacity` | `>=9` `[ASSUMED]` | Retry con backoff (alternativa al retry manual) | OPCIONAL. STACK.md ya lo listó como "missing piece" para el gateway. **Recomendación: retry manual** porque cada retry debe re-pasar el gate de presupuesto (D-25) — un decorador `@retry` no tiene hook natural para eso. Si se adopta tenacity, NO usar `@retry` sin `stop=`/`wait=`/`retry=` explícitos (retry infinito por default). |
| `respx` | `>=0.22` `[ASSUMED]` | Mockear httpx en tests de providers reales | Patrón natural del hexágono: intercepta las llamadas httpx sin red. Para los success criteria, los FakeProvider cubren el grueso; respx valida que el shape del request real sea correcto. |
| `pytest-asyncio` | `>=1.0` `[ASSUMED]` | Tests async de `complete`/`ask`/`embed` | Los puertos son `async def`; ya anticipado en STACK.md. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx` directo | SDK `anthropic` + SDK `openai` | **RECHAZADO.** Doble-retry verificado (SDKs reintentan internamente en 429/5xx → choca con D-25 y el re-paso del gate). Dos deps pesadas en vez de una liviana. Tipos del SDK tienden a filtrarse fuera del adapter. |
| `httpx` para Ollama | SDK `ollama` python | httpx mantiene un solo cliente. El endpoint `/api/embed` es un POST JSON trivial — no justifica una dep extra. |
| retry manual | `tenacity` | tenacity es más declarativo pero el re-paso del gate de presupuesto por retry (D-25) es awkward en decorador. Manual = ~25 líneas legibles y auditables. |
| SQLite manual para presupuesto | `detect-secrets` (Yelp) para el minimizer | `detect-secrets` está en STACK.md para el **pipeline de indexación** (Fase 3, KNOW-07), no necesariamente acá. Para el minimizer de salida, los 3-fuentes de D-21 (env exact-match + regex built-in + config) son más simples y fail-closed que cargar el motor de plugins de detect-secrets. Evaluar reuso en Fase 3; acá, regex propio. |

**Installation:**
```bash
# Estas deps van como dependencias de runtime del gateway (NO de core).
uv add httpx
uv add --dev respx pytest-asyncio
# tenacity SOLO si se decide no hacer retry manual:
# uv add tenacity
```

**Version verification:** No se pudo correr `uv pip index versions` ni `npm view` — **el sandbox bloquea acceso de red a los registries** (probado: comandos retornaron vacío). Todas las versiones arriba están marcadas `[ASSUMED]`. El planner DEBE confirmar cada versión con `uv add <pkg>` (que resuelve y pinea en `uv.lock`) como primer task de instalación, igual que se hizo en Fase 1 (ver STATE.md: "versiones de libs a confirmar con `uv add`").

## Package Legitimacy Audit

> slopcheck no disponible (sin red en sandbox). Todos los paquetes externos quedan `[ASSUMED]`; el planner debe confirmar cada uno con `uv add` (resuelve contra PyPI real y pinea hash en `uv.lock`) antes de usarlo. Los cuatro paquetes abajo son librerías Python establecidas y conocidas — el riesgo de slop es bajo, pero la verificación de versión exacta sigue siendo obligatoria.

| Package | Registry | Age (conocida) | Source Repo | slopcheck | Disposition |
|---------|----------|----------------|-------------|-----------|-------------|
| `httpx` | PyPI | maduro (encode/httpx) | github.com/encode/httpx | n/a (sin red) | `[ASSUMED]` — confirmar con `uv add httpx` |
| `respx` | PyPI | maduro (lundberg/respx) | github.com/lundberg/respx | n/a | `[ASSUMED]` — `uv add --dev respx` |
| `pytest-asyncio` | PyPI | maduro (pytest-dev) | github.com/pytest-dev/pytest-asyncio | n/a | `[ASSUMED]` — `uv add --dev pytest-asyncio` |
| `tenacity` | PyPI | maduro (jd/tenacity) | github.com/jd/tenacity | n/a | `[ASSUMED]` — solo si no se hace retry manual |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck no pudo correr (sandbox sin red). El planner debe gatear cada install detrás de `uv add` que valida contra PyPI real.*

## Architecture Patterns

### System Architecture Diagram

```
AgentModelRequest (agent_id, task_id, tier, purpose, prompt)
        │
        ▼
┌──────────────────────── ModelGateway.ask() ─────────────────────────┐
│  (implementa ModelGatewayPort — lo único que ven los agentes)        │
│                                                                       │
│  1. ModelRouter.resolve(tier) ──► (provider_name, model_alias, max)  │
│        │ tier no existe en config? → error claro, audit, STOP        │
│        ▼                                                              │
│  2. ContextMinimizer.scan(prompt) ──► CLEAN | BLOCKED                 │
│        │ secreto detectado (env-value | regex | config-pattern)?     │
│        │   → audit(QUÉ patrón, SIN el secreto) → raise → STOP (D-20)  │
│        ▼ (prompt ya minimizado/validado)                             │
│  3. CostTracker.authorize(agent_id, tier, est_tokens) ──► OK | VETO  │
│        │ gasto_mes + est_costo > presupuesto_global  → VETO          │
│        │ gasto_agente + est_costo > presupuesto_agente → VETO        │
│        │   → audit(presupuesto agotado) → raise → STOP (D-18)        │
│        ▼                                                              │
│  4. provider.complete(ModelRequest)  ── async HTTP ──►  [LiteLLM]    │
│        │   con retry D-25: 2x backoff SOLO en timeout/429/5xx,       │   │ localhost:4000
│        │   mismo provider, cada retry RE-PASA el gate (paso 3).      │   │ (OpenAI-compat)
│        │   4xx → fail-fast. Sin fallback de tier (D-17).             │   └─► [Anthropic]
│        ▼                                                                  │ Messages API
│  5. CostTracker.record(tokens_in, tokens_out, costo_calculado)       │
│        │   costo = tokens × precio_de_config (D-24, determinístico)  │
│        ▼                                                              │
│  6. TraceStore.write(prompt POST-min, output, tokens, costo,         │
│        latencia, task_id, agent_id, tier, purpose) → traces.db       │
│        ▼                                                              │
│  7. audit.log(model_call) ─── AuditPort inyectado ───► audit.db      │
│        ▼                                                              │
│  return ModelResponse(text, tokens_in, tokens_out, cost_usd, latency)│
└───────────────────────────────────────────────────────────────────────┘

EmbeddingProvider.embed(texts)  ── async HTTP POST /api/embed ──►  [Ollama localhost:11434]
  (port nuevo — ver Open Question 1; nunca sale contenido personal de la máquina, D-15)
```

### Recommended Project Structure
```
src/gateway/
├── __init__.py          # exporta ModelGateway (la fachada ModelGatewayPort)
├── gateway.py           # ModelGateway.ask() — orquesta los 7 pasos del diagrama
├── router.py            # ModelRouter: tier → (provider, model_alias, max_tokens)
├── minimizer.py         # ContextMinimizer: scan fail-closed (3 fuentes, D-21)
├── secrets_patterns.py  # BUILTIN_SECRET_PATTERNS: Final[tuple[...]] (como BUILTIN_DENY)
├── cost.py              # CostTracker: authorize() veta + record() persiste
├── traces.py            # TraceStore: sink SQLite separado (replica audit/sqlite_logger.py)
├── traces_schema.py     # DDL de traces.db (replica audit/schema.py)
└── providers/
    ├── __init__.py
    ├── litellm.py       # LiteLLMProvider (httpx, OpenAI-compatible)
    ├── anthropic.py     # AnthropicProvider (httpx, Messages API)
    ├── ollama.py        # OllamaEmbeddingProvider (httpx, /api/embed)
    └── fakes.py         # FakeModelProvider, FakeEmbeddingProvider (o reusar tests/ports/fakes.py)
```

### Pattern 1: Provider adapter con httpx, tipos de dominio en la frontera
**What:** Cada provider implementa `ModelProvider.complete(ModelRequest) -> ModelResponse`. Recibe/devuelve SOLO dataclasses de dominio; el JSON del SDK/API se traduce DENTRO del adapter.
**When to use:** Los dos providers reales + el de embeddings.
**Example:**
```python
# src/gateway/providers/anthropic.py
# Source: https://platform.claude.com/docs/en/api/messages [CITED]
import time
import httpx
from core.domain import ModelRequest, ModelResponse

class AnthropicProvider:
    def __init__(self, client: httpx.AsyncClient, api_key: str, *, version: str = "2023-06-01") -> None:
        self._client = client
        self._headers = {
            "x-api-key": api_key,                # [VERIFIED: platform.claude.com/docs/en/api/messages]
            "anthropic-version": version,        # header requerido
            "content-type": "application/json",
        }

    @property
    def name(self) -> str:
        return "anthropic"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        resp = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers=self._headers,
            json={
                "model": request.model_alias,
                "max_tokens": request.max_tokens,
                "messages": [{"role": "user", "content": request.prompt}],
            },
        )
        resp.raise_for_status()           # transientes (429/5xx) los maneja el retry de afuera
        data = resp.json()
        # text: content[] con type "text" [VERIFIED: docs anthropic messages]
        text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        usage = data["usage"]             # input_tokens / output_tokens [VERIFIED]
        return ModelResponse(
            text=text,
            tokens_in=usage["input_tokens"],
            tokens_out=usage["output_tokens"],
            cost_usd=0.0,                 # el costo lo calcula CostTracker (D-24), no el provider
            latency_ms=int((time.monotonic() - started) * 1000),
        )
```

```python
# src/gateway/providers/litellm.py
# Source: https://docs.litellm.ai/docs/proxy/user_keys + .../completion/usage [CITED]
class LiteLLMProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str, master_key: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._headers = {"authorization": f"Bearer {master_key}"}  # master_key requerido (verificado en config del owner)

    @property
    def name(self) -> str:
        return "litellm"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        resp = await self._client.post(
            self._url, headers=self._headers,
            json={
                "model": request.model_alias,   # p.ej. "gemini-default", "deepseek-default", "qwen-default"
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data["usage"]   # OpenAI shape: prompt_tokens / completion_tokens / total_tokens [VERIFIED: litellm docs]
        return ModelResponse(
            text=text,
            tokens_in=usage["prompt_tokens"],
            tokens_out=usage["completion_tokens"],
            cost_usd=0.0,        # CostTracker calcula; si data trae "response_cost" se guarda como comparativo (D-24)
            latency_ms=int((time.monotonic() - started) * 1000),
        )
```

### Pattern 2: Minimizer fail-closed con BUILTIN aditivo (mismo patrón que BUILTIN_DENY)
**What:** Patrones de secreto built-in en código como `Final[tuple]`, config solo AGREGA. Idéntico a cómo `bootstrap/config.py` hace `deny = BUILTIN_DENY + config_deny`.
**When to use:** ContextMinimizer (GATE-03).
**Example:**
```python
# src/gateway/secrets_patterns.py  — built-in, NUNCA vaciable por config (D-21, regla #4/#8)
import re
from typing import Final

# Verificado contra prefijos conocidos (gitleaks/secrets-patterns-db) [CITED]
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
```python
# src/gateway/minimizer.py
class SecretDetected(Exception):  # o reusar WyssError-derivada en core.domain.errors
    def __init__(self, pattern_name: str) -> None:  # NUNCA recibe el secreto en sí (D-20)
        super().__init__(f"payload bloqueado: matcheó patrón de secreto '{pattern_name}'")
        self.pattern_name = pattern_name

class ContextMinimizer:
    def __init__(self, env_values: frozenset[str], config_patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> None:
        # env_values = valores reales del .env cargados al boot (match exacto/substring), D-21
        self._env_values = frozenset(v for v in env_values if len(v) >= 8)  # evita match de strings triviales
        self._patterns = BUILTIN_SECRET_PATTERNS + config_patterns          # aditivo

    def scan(self, prompt: str) -> str:
        for value in self._env_values:
            if value in prompt:
                raise SecretDetected("env_value")          # no nombra el valor
        for name, pat in self._patterns:
            if pat.search(prompt):
                raise SecretDetected(name)
        return prompt
```

### Pattern 3: CostTracker veta ANTES, registra DESPUÉS (pre-autorización)
**What:** `authorize()` lee gasto acumulado del mes (SQLite), suma costo estimado, compara contra presupuesto global Y por-agente; veta si excede. `record()` persiste el costo real tras la llamada. Cada retry (D-25) re-llama `authorize()`.
**When to use:** GATE-04. Pitfall central: si el chequeo es post-llamada, el presupuesto es advisory, no enforced (PITFALLS Área 6).
**Example:**
```python
class BudgetExceeded(Exception): ...   # deriva de WyssError

class CostTracker:
    def __init__(self, db_path, prices: dict[str, float], global_budget: float,
                 agent_budgets: dict[str, float], audit) -> None: ...

    def estimate_cost(self, model_alias: str, est_tokens_in: int, est_tokens_out: int) -> float:
        price = self._prices[model_alias]   # tabla local (D-24); KeyError = config incompleta = fail-fast
        return (est_tokens_in + est_tokens_out) / 1000 * price   # esquema exacto a discreción

    def authorize(self, agent_id: str, model_alias: str, est_in: int, est_out: int) -> None:
        est = self.estimate_cost(model_alias, est_in, est_out)
        if self._month_spend() + est > self._global_budget:
            raise BudgetExceeded("presupuesto global mensual agotado")   # D-18
        cap = self._agent_budgets.get(agent_id)
        if cap is not None and self._month_spend_agent(agent_id) + est > cap:
            raise BudgetExceeded(f"presupuesto del agente {agent_id} agotado")
```

### Anti-Patterns to Avoid
- **Doble retry:** envolver un SDK (`anthropic`/`openai`) que ya reintenta, en otro retry. Verificado como causa de gasto descontrolado y bypass del gate. → usar httpx sin retry interno.
- **Costo del provider como verdad del gate:** confiar en `response_cost`/`usage.cost` del provider para el hard-stop. → costo SIEMPRE calculado local (D-24); el del provider solo se guarda comparativo.
- **Minimizer que redacta en vez de bloquear:** reemplazar el secreto y mandar igual. D-20 es explícito: fail-closed, la llamada NO sale.
- **Loguear el secreto detectado:** el audit/trace registra el NOMBRE del patrón, nunca el valor.
- **Fallback de tier silencioso:** si el provider del tier falla, NO probar otro tier/provider (D-17). Error claro al caller.
- **`gateway` importando el paquete `audit`:** rompe el contrato de independencia de import-linter. Inyectar `AuditPort` (puerto en core), no el sink concreto.
- **Tipos del SDK/JSON filtrados fuera del adapter:** el `dict` del response muere en el adapter; afuera solo viaja `ModelResponse` de dominio.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cliente HTTP async con pooling/timeout | socket/urllib a mano | `httpx.AsyncClient` | Connection pooling, timeouts granulares, base para `respx` en tests. |
| Persistencia de traces durable | archivo JSON propio | SQLite + patrón de `audit/sqlite_logger.py` | WAL, fail-fast, índices por task_id/purpose ya resueltos en Fase 1. |
| Backoff exponencial | `sleep(2**n)` esparcido | retry manual centralizado en `gateway.ask()` (o tenacity) | Cada retry debe re-pasar el gate (D-25); centralizar es la única forma de garantizarlo. |
| Parseo de usage/tokens | contar tokens propio | campos `usage` del response | LiteLLM da `prompt_tokens`/`completion_tokens`; Anthropic da `input_tokens`/`output_tokens`. Verificados. |

**Key insight:** El gateway NO debe hand-rollear lo que ya está resuelto en Fase 1 (patrón SQLite, frozen dataclasses, inyección de AuditPort). El único código verdaderamente nuevo y delicado es el **minimizer fail-closed** y el **gate pre-autorización** — ahí va el foco de los tests de seguridad, no en re-implementar HTTP.

## Runtime State Inventory

> Fase greenfield (rellena stubs vacíos). No hay rename/refactor de estado existente. Aún así se inventarían las piezas de estado NUEVAS que esta fase crea, porque afectan al planner.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `traces.db` (nuevo, separado de audit.db y datos de usuario, D-22). Estado de gasto mensual para el gate (tabla propia en traces.db o db aparte — a discreción). | Crear schema nuevo; código edit. |
| Live service config | LiteLLM en Docker del owner (`localhost:4000`) — modelos definidos en `~/Data/10_Workspace/tools/litellm-local/config.yaml`: `gemini-default`, `gemini-2.5`, `gemini-cheap`, `deepseek-default`, `deepseek-r1`, `qwen-default`, `qwen-cheap`, etc. Requiere `LITELLM_MASTER_KEY` (Bearer). El proxy NO está bajo control del repo. | Los aliases de `config.toml` del gateway deben referenciar nombres que EXISTEN en ese config.yaml. Validar contra `/v1/models` en smoke test. |
| OS-registered state | Ninguno (no hay systemd/cron en esta fase). | None — verificado: la fase no registra servicios OS. |
| Secrets/env vars | `ANTHROPIC_API_KEY` (nuevo, para AnthropicProvider directo); `LITELLM_MASTER_KEY` (ya existe en `.env` del owner para el proxy); claves del proxy (`GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`) viven en el `.env` de litellm-local, NO en el repo wyss. | El `.env` de wyss debe declarar `ANTHROPIC_API_KEY` + `LITELLM_MASTER_KEY`. Documentar en `config/.env.example`. Estos valores alimentan al ContextMinimizer como `env_values` (D-21). |
| Build artifacts | `src/gateway/__init__.py` es stub vacío; al rellenar el módulo, `uv add httpx` modifica `pyproject.toml` + `uv.lock`. | `uv sync` tras agregar deps; reinstalar editable. |

**Nada en categoría OS-registered:** None — verificado, la fase es código + DB nueva, sin registración de servicios.

## Common Pitfalls

### Pitfall 1: Doble retry (SDK + retry propio)
**What goes wrong:** Los SDKs `anthropic`/`openai` reintentan internamente 429/5xx (típ. 2x backoff). Si encima se aplica el retry de D-25, una sola llamada lógica genera hasta 6 intentos reales → gasto y latencia descontrolados, y el gate de presupuesto se evalúa fuera de sincronía.
**Why it happens:** No se sabe que el SDK reintenta por default.
**How to avoid:** Usar httpx directo (sin retry interno) y centralizar el retry en `gateway.ask()`. Si se usara un SDK, desactivar su retry (`max_retries=0`).
**Warning signs:** Latencias multiplicadas; el contador de gasto sube más de lo esperado por llamada.
**Source:** [VERIFIED: WebSearch cross-referenced — github.com/jd/tenacity#254, api4.ai retry best practices]

### Pitfall 2: Presupuesto advisory en vez de enforced
**What goes wrong:** El CostTracker registra costo DESPUÉS de la llamada pero no veta antes → el hard-stop no existe, la primera factura sorpresa llega igual.
**Why it happens:** "Tracking para después" (PITFALLS Área 6).
**How to avoid:** `authorize()` se llama ANTES de `provider.complete()` y puede levantar `BudgetExceeded`. Cada retry re-llama `authorize()`.
**Warning signs:** El test "presupuesto agotado bloquea" no existe o pasa sin que la llamada se haya intentado.

### Pitfall 3: Falsos positivos / negativos en regex de secretos
**What goes wrong:** Regex demasiado laxos bloquean prompts legítimos (hashes, IDs base64); demasiado estrictos dejan pasar el secreto. Multi-línea es el talón de Aquiles (gitleaks procesa línea por línea).
**Why it happens:** Entropía pura tiene baja precisión; regex sin anclaje matchea placeholders.
**How to avoid:** Anclar por prefijo conocido (`sk-ant-`, `AKIA`, `ghp_`) que tiene baja tasa de falso positivo; el match exacto de valores del `.env` (D-21) es la red de seguridad de alta precisión. PEM/private key match por header multilínea explícito. Test del "secreto trampa" con varios formatos.
**Warning signs:** El fixture trampa pasa (secreto sale) o prompts normales se bloquean en dev.
**Source:** [CITED: github.com/gitleaks/gitleaks, secrets-patterns-db (mazinahmed.net)]

### Pitfall 4: `gateway` rompiendo el contrato de import-linter
**What goes wrong:** `import audit` en `gateway/` → falla `lint-imports` (contrato `independence`).
**How to avoid:** El gateway depende del puerto `AuditPort` (`core/ports/audit.py`), inyectado por bootstrap. El `SqliteAuditLogger` concreto NUNCA se importa desde `gateway/`. Igual para `traces.db`: el sink vive DENTRO de `gateway/` (no en `audit/`), porque traces ≠ audit (D-22).
**Warning signs:** `uv run lint-imports` rojo tras agregar el cableado.

### Pitfall 5: Mutar AgentModelRequest frozen rompe tests de Fase 1
**What goes wrong:** Extender `AgentModelRequest` (D-26: agregar `tier`, `purpose`) es un cambio en dominio frozen consumido por `tests/ports/fakes.py` y `tests/ports/test_conformance.py`.
**How to avoid:** Agregar `tier: str` y `purpose: str` como campos nuevos (con defaults si hace falta para no romper construcciones existentes). Actualizar `FakeModelGatewayPort` y los tests de conformance en el mismo task. Verificar `mypy --strict` y la suite de Fase 1 verde.
**Warning signs:** `tests/ports/test_conformance.py` rojo; mypy se queja de argumento faltante.

### Pitfall 6: SQLite WAL falla sobre NTFS/fuseblk
**What goes wrong:** `~/Data` es NTFS (memoria del owner: `/mnt/hdd/Data` automount); WAL puede degradar silenciosamente. El audit logger ya lo maneja fail-fast.
**How to avoid:** `traces.db` debe replicar EXACTO el smoke test WAL de `audit/sqlite_logger.py` (líneas 44-57): verificar `PRAGMA journal_mode` retorna `"wal"` o levantar error. El `data_dir` de runtime debe estar en ext4, no en el mount NTFS.
**Source:** [VERIFIED: codebase — src/audit/sqlite_logger.py + STATE.md decisión 2026-06-11]

## Code Examples

### ModelRouter — resolución determinística tier→provider
```python
# src/gateway/router.py — sin LLM, sin heurística (D-16)
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class TierConfig:
    provider: str       # "litellm" | "anthropic"
    model_alias: str    # "gemini-default" | "claude-opus-4-6" | ...
    max_tokens: int

class ModelRouter:
    def __init__(self, tiers: dict[str, TierConfig]) -> None:
        self._tiers = tiers

    def resolve(self, tier: str) -> TierConfig:
        try:
            return self._tiers[tier]
        except KeyError:
            raise UnknownTier(tier, available=tuple(self._tiers))  # error claro, auditado (D-17)
```

### Ollama embeddings (port nuevo)
```python
# src/gateway/providers/ollama.py
# Source: https://docs.ollama.com/capabilities/embeddings [CITED]
class OllamaEmbeddingProvider:
    def __init__(self, client: httpx.AsyncClient, base_url: str = "http://localhost:11434",
                 model: str = "nomic-embed-text") -> None:
        self._client, self._url, self._model = client, f"{base_url}/api/embed", model

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        resp = await self._client.post(self._url, json={"model": self._model, "input": list(texts)})
        resp.raise_for_status()
        # /api/embed soporta batching (input=array) y devuelve "embeddings" L2-normalizado [VERIFIED]
        return [tuple(vec) for vec in resp.json()["embeddings"]]
```
**Nota crítica:** el puerto `EmbeddingProvider` ya existe en `core/ports/knowledge.py` (`async def embed(texts) -> Sequence[Vector]`). La fase reusa ESE puerto — no inventa uno nuevo. Verificar firma exacta antes de implementar (ver Open Question 1).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SDK por provider (`openai`, `anthropic`) | httpx directo cuando hay retry/gate custom | 2024-2025 | Evita doble-retry; un cliente para N endpoints OpenAI-compatibles. |
| `/api/embeddings` (singular) Ollama | `/api/embed` (batching, L2-normalizado) | 2024 | Usar `/api/embed`; soporta `input` array. |
| `requests` sync + threads | `httpx.AsyncClient` | establecido | Async nativo, encaja con `asyncio` del daemon. |

**Deprecated/outdated:**
- Ollama `/api/embeddings` (singular, sin batching) → usar `/api/embed`.
- Anthropic Text Completions API (legacy) → Messages API (`/v1/messages`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Versiones de libs (`httpx>=0.28`, `respx>=0.22`, `pytest-asyncio>=1.0`, `tenacity>=9`) | Standard Stack | Bajo — `uv add` resuelve la real; solo se pinea distinto. |
| A2 | `nomic-embed-text` es el modelo de embeddings (768 dims) | Open Questions / Ollama | Medio — Ollama NO está instalado (ver Environment). Modelo a confirmar/descargar; `embeddinggemma`/`qwen3-embedding` son alternativas verificadas en docs oficiales. |
| A3 | El alias `claude-opus-4-6` / nombre de modelo Anthropic a usar | router/anthropic | Medio — depende del plan/tier del owner; el modelo exacto va en `config.toml` (discrecional). |
| A4 | Anthropic 429/529/500 son los códigos transientes | retry D-25 | Bajo — la doc oficial no listó códigos de error en el excerpt; 429/5xx es convención sólida y `raise_for_status` + clasificación por rango cubre el caso. |
| A5 | El `.env` de wyss tendrá `ANTHROPIC_API_KEY` y `LITELLM_MASTER_KEY` | Runtime State | Bajo — es decisión de config del owner; documentar en `.env.example`. |
| A6 | Reusar `EmbeddingProvider` de `core/ports/knowledge.py` (no port nuevo) | Code Examples | Bajo — verificado que existe; confirmar firma exacta (Open Q1). |

## Open Questions (RESOLVED)

1. **¿`AgentModelRequest` lleva `max_tokens`/límite de tokens, o sale del tier config?**
   - What we know: `ModelRequest` (provider) tiene `max_tokens`; `AgentModelRequest` (agente) hoy solo tiene agent_id/task_id/prompt. D-26 agrega tier + purpose.
   - What's unclear: si el `max_tokens` lo fija el tier (config) o el caller.
   - Recommendation: el tier lo fija (`TierConfig.max_tokens`) — el caller solo declara tier+purpose. Confirmar en planning.

2. **¿El `EmbeddingProvider` (Ollama) entra en esta fase o solo el contrato + fake?**
   - What we know: success criterion 5 pide "EmbeddingProvider funciona con al menos un proveedor real y uno fake". El puerto existe en `core/ports/knowledge.py`.
   - What's unclear: Ollama NO está instalado en la máquina (verificado). El criterio "un proveedor real" requiere instalarlo + descargar modelo.
   - Recommendation: incluir un task de provisión (instalar Ollama + `ollama pull nomic-embed-text`) o marcar el test real como `skipif` opt-in (patrón ya usado para NTFS: `WYSS_TEST_NTFS`), con el fake cubriendo CI. Decidir en discuss/planning.

3. **¿Estado de gasto en `traces.db` o DB propia?**
   - Recommendation: tabla propia dentro de `traces.db` (una sola DB de gateway, separada de audit y de datos de usuario, cumple D-22). A discreción del schema (D-22 lo permite).

4. **¿`ANTHROPIC_API_KEY` real disponible?** El sandbox no permite verificar conectividad. El owner debe confirmar que tiene plan/clave Anthropic activa para el tier fuerte, o el tier fuerte se mapea temporalmente vía LiteLLM (el config.yaml del owner ya tiene aliases `claude-sonnet-4-5`/`claude-opus-4-5` que apuntan a gemini — workaround del owner, NO usar para el AnthropicProvider directo).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | todo | ✓ | 3.14.5 (pyproject pide >=3.12) | — |
| `uv` | gestión deps | ✓ | 0.11.18 | — |
| LiteLLM proxy (`localhost:4000`) | LiteLLMProvider (GATE-01) | ✓ config presente | Docker `main-latest` | El proxy puede estar apagado (memoria owner: Docker n8n/litellm con autostart off por perf). Levantar a mano antes del smoke test real. |
| Ollama (`localhost:11434`) | EmbeddingProvider real (criterion 5) | ✗ **no instalado** | — | **BLOQUEANTE para el test "real":** instalar Ollama + `ollama pull nomic-embed-text`, o marcar test real `skipif` y cubrir CI con FakeEmbeddingProvider. |
| `ANTHROPIC_API_KEY` | AnthropicProvider (tier fuerte) | ? no verificable (sandbox) | — | Confirmar con el owner; sin clave el provider no hace la llamada real (test con respx/fake igual valida el shape). |
| Acceso de red a PyPI | `uv add` de deps | ✗ en sandbox | — | El planner corre `uv add` fuera del sandbox (entorno del owner tiene red). |

**Missing dependencies with no fallback:**
- Acceso de red durante research (registries) — resuelto: el planner verifica versiones con `uv add` en el entorno real.

**Missing dependencies with fallback:**
- Ollama no instalado → fallback: test real opt-in (`skipif`), fake en CI. Requiere task de provisión si se quiere el criterion 5 "real" verde.
- LiteLLM apagado → levantar el contenedor antes del smoke test de integración.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=9` (+ `pytest-asyncio` `[ASSUMED]` para tests async) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=["tests"], marker `ntfs` ya existe) |
| Quick run command | `uv run pytest tests/gateway -x -q` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check && uv run lint-imports` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GATE-01 | Dos providers intercambiables por config; FakeProvider sustituible | unit + integration | `uv run pytest tests/gateway/test_providers.py -x` | ❌ Wave 0 |
| GATE-02 | tier→provider determinístico; tier inexistente → error claro | unit | `uv run pytest tests/gateway/test_router.py -x` | ❌ Wave 0 |
| GATE-03 | "secreto trampa" (env-value + sk-ant- + AKIA + JWT + PEM) NUNCA en payload; fail-closed | **security** | `uv run pytest tests/gateway/test_minimizer.py -x` | ❌ Wave 0 |
| GATE-04 | presupuesto agotado → `BudgetExceeded` ANTES de la llamada; provider nunca invocado | **security** | `uv run pytest tests/gateway/test_cost_gate.py -x` | ❌ Wave 0 |
| GATE-05 | cada llamada deja trace consultable (prompt post-min, output, tokens, costo, latencia); retención 90d | integration | `uv run pytest tests/gateway/test_traces.py -x` | ❌ Wave 0 |
| GATE-01/05 | EmbeddingProvider real (Ollama) + fake | integration (opt-in) + unit | `WYSS_TEST_OLLAMA=1 uv run pytest tests/gateway/test_embeddings.py` | ❌ Wave 0 |
| D-25 | retry 2x SOLO transientes; 4xx fail-fast; cada retry re-pasa gate | unit (respx simula 429→200) | `uv run pytest tests/gateway/test_retry.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/gateway -x -q`
- **Per wave merge:** `uv run pytest && uv run mypy`
- **Phase gate:** full suite verde (incl. `lint-imports` — el contrato `core puro` y `independence` NO deben romperse) antes de `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/gateway/__init__.py` + `tests/gateway/conftest.py` — fixtures: AsyncClient mockeado (respx), FakeAuditPort (reusar de `tests/ports/fakes.py`), tmp_path para traces.db.
- [ ] `tests/gateway/test_minimizer.py` — fixture "secreto trampa" multi-formato (GATE-03, criterion 2).
- [ ] `tests/gateway/test_cost_gate.py` — presupuesto agotado bloquea (GATE-04, criterion 3).
- [ ] Framework install: `uv add --dev pytest-asyncio respx` (confirma versiones).
- [ ] Decisión Ollama: task de provisión o `skipif WYSS_TEST_OLLAMA` (criterion 5).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication (a APIs externas) | yes | API keys vía env (`ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`); Bearer/x-api-key headers; nunca en código ni en traces. |
| V5 Input Validation / Output Encoding | yes | ContextMinimizer fail-closed (GATE-03): el prompt saliente se valida contra fuga de secretos antes de cruzar la frontera de red. |
| V6 Cryptography | no (no se hace cripto propia) | — (no hand-roll; detección de PEM private keys es para BLOQUEAR, no operar). |
| V7 Error Handling / Logging | yes | Errores auditados sin filtrar secretos (D-20: nombre del patrón, no el valor); traces separados de audit (D-22). |
| V8 Data Protection | yes | Embeddings de contenido personal vía Ollama LOCAL (D-15) — nunca salen de la máquina. Minimización de contexto (regla #4). |
| V11 Business Logic | yes | Gate de presupuesto pre-autorización (GATE-04); sin auto-override (regla #6, D-19). |

### Known Threat Patterns for httpx + LLM providers

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Exfiltración de secretos vía prompt a API externa | Information Disclosure | ContextMinimizer fail-closed, 3 fuentes (D-20/21). Fixture trampa en tests. |
| Secreto logueado en trace/audit | Information Disclosure | Auditar nombre de patrón, nunca el valor; traces guardan prompt POST-minimizer (D-22). |
| Gasto descontrolado (DoW — denial of wallet) | Denial of Service | Gate hard-stop pre-autorización + retry limitado 2x que re-pasa el gate (D-18/24/25). |
| Fallback silencioso cambia costo/calidad sin decisión humana | Tampering / Repudiation | Fail-fast sin fallback de tier (D-17); destrabe solo por config + reload, auditado (D-19). |
| Prompt injection vía contenido recuperado eleva privilegios del gateway | Elevation of Privilege | Fuera de scope de esta fase (POL-07, Fase 7); el gateway no interpreta el contenido, solo lo transporta minimizado. |
| API key en repo/`.env` commiteado | Information Disclosure | `.env` gitignoreado; solo `.env.example` con placeholders; keys del proxy viven en litellm-local, no en wyss. |

## Sources

### Primary (HIGH confidence)
- Codebase verificado (lectura directa): `src/core/ports/gateway.py`, `src/core/domain/gateway.py`, `src/audit/sqlite_logger.py`, `src/audit/schema.py`, `src/bootstrap/config.py`, `src/core/ports/audit.py`, `tests/ports/fakes.py`, `pyproject.toml` (contratos import-linter).
- `.planning/research/ARCHITECTURE.md` (Flow 4, Pattern 4 composition root, Interface Contracts), `PITFALLS.md` (Área 6), `STACK.md`.
- `~/Data/10_Workspace/tools/litellm-local/config.yaml` + `docker-compose.yml` — modelos reales y auth del proxy del owner (verificado).
- https://platform.claude.com/docs/en/api/messages — request/response/usage/headers de Messages API [CITED].
- https://docs.ollama.com/capabilities/embeddings — `/api/embed` shape, L2-normalizado, batching [CITED].
- https://docs.litellm.ai/docs/completion/usage + .../docs/proxy/user_keys — usage OpenAI shape, Bearer master_key [CITED].

### Secondary (MEDIUM confidence)
- github.com/anthropics/anthropic-sdk-python (releases) — error types (OverloadedError, RateLimitError…); SDK no usado pero informa la taxonomía [WebSearch verified].
- Retry best practices: github.com/jd/tenacity#254, api4.ai blog, ai.pydantic.dev/retries — doble-retry de SDKs verificado cross-source.

### Tertiary (LOW confidence — marcado para validación)
- Versiones exactas de paquetes (sandbox sin red a PyPI) — confirmar con `uv add`.
- Disponibilidad real de LiteLLM/Ollama/ANTHROPIC_API_KEY en runtime — confirmar en el entorno del owner.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (httpx vs SDK decidido con evidencia cross-source; versiones `[ASSUMED]` por sandbox).
- Architecture: HIGH (contratos de Fase 1 leídos directo; import-linter constraints verificados).
- Pitfalls: HIGH (doble-retry y advisory-budget verificados contra fuentes + PITFALLS.md del repo).
- Provider API shapes: HIGH (Anthropic/Ollama/LiteLLM contra docs oficiales).
- Environment: MEDIUM (Ollama confirmado ausente; LiteLLM config confirmado presente pero conectividad no verificable en sandbox).

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (APIs estables; revalidar versiones de libs al instalar)
