# Phase 5: Orquestador Daemon — Research

**Researched:** 2026-06-13
**Domain:** Python asyncio daemon, MCP server, Hermes Agent integration, SQLite pending queue, async confirmation flow, policy golden eval
**Confidence:** HIGH (architecture and code patterns verified against existing codebase and official sources)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Frontera Hermes ↔ política determinística (ORCH-03, POL-06)**
- D-50: Hermes propone, engine dispone. Hermes clasifica intención y draftea el Plan; el nivel A/B/C/D lo asigna el `CognitivePolicyEngine` determinístico (puro, sin LLM, ya existe). La categoría de intención puede venir de Hermes; el nivel jamás.
- D-51: Hermes emite un Plan estructurado (`core.domain.plan.Plan` / `Action`), no texto libre.
- D-52: Nivel dinámico por `(action_type, target/args)` vía denylist-as-data. Mismo `file.delete` es A en `/tmp` y C/D en `~/Data`.
- D-53: La garantía anti-falso-A vive en el engine determinístico, no en Hermes.

**Confirmación async + persistencia (ORCH-04, ORCH-05, ORCH-06)**
- D-54: Patrón pending-id + reconnect. `wyss ask` → daemon arma Plan → `engine.evaluate` → si `outcome=CONFIRM` persiste `pending_proposal` en SQLite y responde con Plan legible + `pending_id`.
- D-55: Cola de pendientes como fuente de verdad en SQLite — un restart no pierde confirmaciones.
- D-56: TTL configurable con auto-reject + audit. Las propuestas expiran; al vencer → auto-reject + entrada de auditoría.
- D-57: Tras `wyss confirm`, el despacho se encola (Fase 6 ejecuta); `confirm` responde aceptado + execution-id. El daemon nunca bloquea en la ejecución.

**Lifecycle Hermes + MCP server (ORCH-01)**
- D-58: Hermes desacoplado — container Hermes + docker compose aparte. El daemon es cliente detrás de `OrchestratorPort`. `wyss start` levanta solo el daemon.
- D-59: El MCP server de Wyss lo hostea el daemon (socket local que el container Hermes alcanza). Cada call MCP de Hermes → `CognitivePolicyEngine` + audit.
- D-60: Degradación D-44: si Hermes está down, el daemon responde explícito ("orquestador no disponible"). Las consultas determinísticas (`knowledge_query` directa al Retrieval de Fase 4) pueden seguir.
- D-61: `wyss start` sobrevive a socket huérfano (detecta + limpia stale socket). systemd reinicia el daemon ante fallo.

**Errores por paso + eval dorado (ORCH-07, POL-06)**
- D-62: Política de error declarada en el Plan schema — cada `Action` lleva `on_error: retry|escalate|abort` + backoff params. Fase 5 define el schema; Fase 6 lo ejecuta.
- D-63: Eval set dorado anti-falso-A réplica del gate `hit@1=20/20` de Fase 4: fixtures `NL → nivel esperado`, corre en CI; cualquier falso-A rompe el build.

### Claude's Discretion

- Esquema concreto de las tablas SQLite de colas (`pending_proposals`, etc.) y nombres de métodos JSON-RPC.
- Formato de salida de `wyss audit`.
- Transport exacto del MCP server (stdio vs socket TCP local) — decidir en research según cómo el container Hermes alcanza al host.
- Naming de los agentes (identidad argentina) — configuración, no código.

### Deferred Ideas (OUT OF SCOPE)

- Enforcement de ejecución (retry/backoff/abort real, la `Tool` port): Fase 6.
- Rutinas / triggers programados: fase posterior.
- Agentes de dominio con nombre (Belgrano, Sarmiento): fase posterior.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORCH-01 | `wyss start` levanta el daemon (Unix socket + JSON-RPC, asyncio); corre persistente sin intervención | Daemon architecture section: asyncio.start_unix_server + stale socket pattern |
| ORCH-02 | `wyss ask "<instrucción>"` envía lenguaje natural al daemon y recibe respuesta | JSON-RPC client pattern from CLI; daemon dispatch loop |
| ORCH-03 | Intent Router clasifica en ≥9 categorías | Hermes → OrchestratorPort adapter; LLM-based classification piped through engine |
| ORCH-04 | Ante instrucción ambigua el sistema pide aclaración | Intent category `ambiguous_request` → clarification response, no Plan generated |
| ORCH-05 | Toda tarea modificadora genera un Plan explícito y legible antes de ejecutarse | Plan schema + Rich rendering pattern; existing `Plan`/`Action` domain objects |
| ORCH-06 | Las colas de pendientes viven en SQLite — restart no pierde nada | `pending_proposals` table schema in SQLite |
| ORCH-07 | Política de errores explícita por paso: retry/escalate/abort — fallas no silenciosas | `Action.on_error` + `ErrorPolicy` schema extension (D-62) |
| POL-06 | Eval set del clasificador: falso-A detectado en CI | Replicate `tests/policy/test_golden_plans.py` gate pattern |
| AUD-02 | El owner puede consultar el historial de acciones | `wyss audit` command over existing `audit_events` SQLite table |
</phase_requirements>

---

## Summary

La Fase 5 construye el daemon persistente de Wyss: un proceso asyncio sobre Unix socket (JSON-RPC 2.0) que recibe lenguaje natural del owner, lo clasifica vía Hermes Agent en un container Docker aislado, genera un `Plan` estructurado, lo evalúa con el `CognitivePolicyEngine` determinístico existente, y ejecuta el flujo A/B/C/D con persistencia SQLite de las confirmaciones pendientes.

La arquitectura tiene tres piezas que encajan limpiamente: (1) **daemon central** — asyncio, Unix socket JSON-RPC, SQLite pending queue, systemd unit; (2) **Hermes como OrchestratorPort** — container Docker con built-in tools deshabilitados (`disabled_toolsets: [all]`), conectado al MCP server del daemon vía HTTP Streamable (`http://host-gateway:PORT/mcp`), modelo configurable por `config.yaml`; (3) **MCP server en el daemon** — FastMCP con transporte `streamable-http`, gateado fail-closed por `CognitivePolicyEngine` + audit antes de registrar cualquier herramienta.

La decisión de transport del MCP server (la más incierta) se resuelve con **Streamable HTTP en puerto local TCP** (e.g. `127.0.0.1:7420`) en vez de Unix socket, porque el container Hermes necesita cruzar el namespace de red. Desde el container se conecta usando `host.docker.internal:7420` (Linux Docker con `--add-host=host.docker.internal:host-gateway`). Esto mantiene el invariante: todo call MCP pasa por el daemon, nunca escapa a servicios externos.

**Recomendación primaria:** Implementar el MCP server con `fastmcp` 2.x (streamable HTTP, `host="127.0.0.1"`, puerto configurable), el daemon con `asyncio.start_unix_server` + `jsonrpcserver` para el IPC CLI, la cola de pendientes como tabla SQLite directo con `sqlite3` stdlib (patron ya establecido), y el gate dorado POL-06 como extensión directa de `tests/policy/test_golden_plans.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Daemon lifecycle (start/stop/restart) | Daemon process (asyncio) | systemd user unit | El proceso principal es el daemon; systemd es el supervisor |
| CLI IPC (`wyss ask`, `wyss confirm`) | Unix socket JSON-RPC | CLI (Typer) como cliente | CLI es thin client; toda la lógica vive en el daemon |
| Intent classification (NL → categoría) | Hermes container (LLM) | OrchestratorPort adapter | Hermes hace NL bien; el adapter traduce a dominio Wyss |
| Plan generation (NL → Plan struct) | Hermes container (LLM) | OrchestratorPort adapter | Hermes draft el plan; el engine lo evalúa |
| Policy enforcement (nivel A/B/C/D) | CognitivePolicyEngine (deterministic) | — | D-50/D-53: el engine nunca delega al LLM |
| MCP server (tool surface de Hermes) | Daemon process (FastMCP) | — | D-59: el daemon hostea el MCP server para gating en un solo proceso |
| MCP tool gating (policy + audit) | Daemon process (CognitivePolicyEngine) | AuditLogger | Cada call MCP pasa por el engine antes de registrarse |
| Pending proposal persistence | SQLite (stdlib) | — | D-55: fuente de verdad; mismo patrón que audit_events |
| TTL auto-reject | Daemon background task (asyncio) | AuditLogger | Poller periódico en el event loop; registra rechazo |
| Audit query (`wyss audit`) | CLI + SQLite (AuditPort) | Rich console | AUD-02: sobre la tabla `audit_events` ya existente |
| Golden eval (POL-06) | pytest CI | — | D-63: tests determinísticos, no integración con Hermes |
| Orchestrator knowledge fallback | HybridRetrieval (Fase 4) | — | D-60: sigue vivo si Hermes está down |

---

## Standard Stack

### Core (ya en pyproject.toml — sin instalar nada nuevo)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio` (stdlib) | Python 3.12 | Event loop, Unix socket server | Stdlib; `asyncio.start_unix_server` hace el 90% del daemon |
| `sqlite3` (stdlib) | Python 3.12 | Pending proposals queue | Mismo patrón que audit_events; sin deps extra |
| `json` (stdlib) | Python 3.12 | JSON-RPC serialization | Daemon IPC de ~100 líneas sin framework |
| `typer` | ≥0.26.7 | CLI commands: start/ask/confirm/audit | Ya en stack; añadir subcomandos a `cli.py` |
| `rich` | ≥15.0.0 | Plan rendering, confirmación B/C, audit output | Ya en stack |
| `httpx` | ≥0.28.1 | OrchestratorPort → Hermes API (async HTTP) | Ya en stack; gateway ya lo usa |
| `pydantic` (v2) | ≥2.13 | Config validation en bootstrap; Hermes response schema | Ya en stack; solo en bootstrap |

### Nuevas dependencias (a agregar)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `mcp` | 1.27.2 | MCP Python SDK — server-side Protocol types | SDK oficial del protocolo MCP [VERIFIED: npm registry] |
| `fastmcp` | 2.14.x | FastMCP server framework — streamable HTTP transport | Capa de conveniencia sobre `mcp`; `@mcp.tool()` decorator, `mcp.run(transport="http")` [VERIFIED: PyPI] |

**Nota sobre fastmcp:** La versión 3.x (3.4.2 en PyPI) cambió la API de forma breaking respecto a 2.x. Usar la serie 2.14.x que es la última de la generación estable. Verificar con `uv add "fastmcp>=2.14,<3"` antes de instalar.

### Alternativas consideradas

| En vez de | Podría usarse | Tradeoff |
|-----------|---------------|----------|
| FastMCP streamable HTTP | `mcp` SDK puro con starlette | FastMCP ya integra el transporte; usar SDK puro requiere wiring manual de ASGI |
| `jsonrpcserver` para IPC | Implementación manual JSON-RPC 2.0 | El daemon IPC es ~100 líneas de `asyncio`+`json` sin framework; `jsonrpcserver` agrega una dep para algo trivial. Se recomienda **implementación manual** sobre el stdlib. |
| Docker host networking | `--add-host=host.docker.internal:host-gateway` | Host networking da acceso total a la red del host; add-host es más quirúrgico y portable |

**Decisión de transport MCP:** Streamable HTTP (TCP local `127.0.0.1:PORT`), NO Unix socket, porque el container Hermes cruza el namespace de red. FastMCP expone `http://127.0.0.1:7420/mcp`; el container conecta con `http://host.docker.internal:7420/mcp`.

### Hermes Agent (externo, no como dep Python)

| Componente | Versión | Rol |
|------------|---------|-----|
| `hermes-agent` (NousResearch) | v0.16.0 | Cerebro de orquestación NL, corre en container Docker aparte |
| Docker Compose | — | Orquesta container Hermes; prerequisito documentado |

**Installation:**
```bash
# Nuevas deps Python del proyecto
uv add "mcp>=1.27,<2" "fastmcp>=2.14,<3"

# Hermes Agent (fuera del proyecto Python)
docker pull ghcr.io/nousresearch/hermes-agent:latest  # confirmar imagen en repo
```

---

## Package Legitimacy Audit

| Package | Registry | slopcheck | Disposition |
|---------|----------|-----------|-------------|
| `mcp` | PyPI 1.27.2 | [OK] | Approved — paquete oficial del Model Context Protocol |
| `fastmcp` | PyPI 2.14.7 | [OK] | Approved — framework popular sobre `mcp` SDK |
| `jsonrpcserver` | PyPI 5.0.9 | [OK] | Considerado pero NO recomendado — daemon IPC se implementa sobre stdlib (ver arriba) |

**Packages removed due to [SLOP]:** none
**Packages flagged [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Owner
  │  CLI (Typer)
  │  wyss ask "..." / wyss confirm <id> / wyss audit
  ▼
Unix Socket (wyss.sock)
  │  JSON-RPC 2.0 (asyncio)
  ▼
DAEMON (src/orchestrator/daemon.py)
  │
  ├─► IntentRouter → OrchestratorPort.classify(nl_text)
  │       │                    │ HTTP POST /v1/chat/completions
  │       │              HERMES CONTAINER (Docker)
  │       │              tools: only mcp_wyss_* (MCP gated)
  │       │                    │ MCP calls → http://host-gateway:7420/mcp
  │       │                    ▼
  │       │           MCP SERVER (FastMCP, in daemon)
  │       │           @mcp.tool("knowledge_query") etc.
  │       │                    │ EVERY call →
  │       │           CognitivePolicyEngine.evaluate(plan)
  │       │                    │ + AuditLogger
  │       │                    │
  │       ◄── Plan (structured) ────────────────────────────┘
  │
  ├─► CognitivePolicyEngine.evaluate(plan) → PolicyDecision
  │       outcome: EXECUTE → dispatch queue (Fase 6)
  │       outcome: CONFIRM_SIMPLE / CONFIRM_STRONG →
  │           pending_proposals SQLite (pending_id, plan, level, expiry_at)
  │           respond: plan_readable + pending_id
  │       outcome: REJECT →
  │           AuditLogger + refuse response
  │
  ├─► TTL Background Task (asyncio)
  │       polls pending_proposals WHERE expiry_at < now()
  │       → auto-reject + AuditLogger
  │
  └─► AuditLogger (SqliteAuditLogger, existing)

wyss confirm <id>   → daemon → load pending_proposal → B: [s/N] / C: "CONFIRMAR"
                    → dispatch queue entry + execution-id → respond accepted
wyss audit [--since] → CLI queries audit_events directly (AUD-02)
```

### Recommended Project Structure

```
src/
├── orchestrator/
│   ├── __init__.py          # re-export daemon entry point
│   ├── daemon.py            # asyncio Unix socket server, main loop (ORCH-01)
│   ├── dispatcher.py        # route PolicyDecision to execute/confirm/reject
│   ├── intent_router.py     # IntentRouter: NL → IntentClassification (9 categories)
│   ├── mcp_server.py        # FastMCP server (MCP tools gated by engine) (D-59)
│   ├── orchestrator_port.py # OrchestratorPort Protocol (nueva, en core/ports/)
│   ├── pending_store.py     # SQLite pending_proposals queue (D-54..D-56)
│   ├── plan_renderer.py     # Human-readable plan (Rich panels for B/C prompts)
│   └── ttl_reaper.py        # Background asyncio task: expire + auto-reject (D-56)
├── core/
│   └── ports/
│       └── orchestrator.py  # OrchestratorPort Protocol (nueva — aquí, no en orchestrator/)
├── bootstrap/
│   └── cli.py               # Añadir: start, ask, confirm, audit subcommands
└── adapters/
    └── hermes/
        └── hermes_adapter.py  # HermesOrchestrator implements OrchestratorPort
```

**Nota sobre ubicación de OrchestratorPort:** Según el patrón establecido, los ports viven en `src/core/ports/`. El adapter concreto (HermesOrchestrator) vive en `src/orchestrator/` o en un nuevo `src/adapters/hermes/`.

### Pattern 1: Daemon Unix Socket con stale socket cleanup

**What:** `asyncio.start_unix_server` con detección y limpieza de socket huérfano al arrancar.
**When to use:** Siempre — ORCH-01, D-61.

```python
# Source: Python 3.12 asyncio docs + Python issue #425 (stale socket)
import asyncio
import os
from pathlib import Path

async def _cleanup_stale_socket(path: Path) -> None:
    """Detecta socket huérfano (proceso muerto) y lo elimina (D-61)."""
    if not path.exists():
        return
    # Intenta conectar: si rechaza de inmediato, el socket es huérfano
    try:
        _r, w = await asyncio.open_unix_connection(str(path))
        w.close()
        await w.wait_closed()
        raise RuntimeError(f"Daemon ya corriendo en {path}")
    except (ConnectionRefusedError, FileNotFoundError):
        path.unlink(missing_ok=True)  # stale socket, eliminar

async def run_daemon(socket_path: Path) -> None:
    await _cleanup_stale_socket(socket_path)
    server = await asyncio.start_unix_server(
        handle_client, str(socket_path)
    )
    # Python 3.13+: cleanup_socket=True; en 3.12 hacer unlink en shutdown
    try:
        async with server:
            await server.serve_forever()
    finally:
        socket_path.unlink(missing_ok=True)
```

### Pattern 2: JSON-RPC 2.0 manual sobre asyncio (sin framework)

**What:** Dispatcher minimalista sobre el protocol JSON-RPC 2.0 spec (~100 líneas stdlib).
**When to use:** IPC del daemon con el CLI — ORCH-01, ORCH-02.

```python
# Source: JSON-RPC 2.0 spec (jsonrpc.org) + asyncio streams
import json

METHODS: dict[str, Callable] = {}

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        raw = await reader.readline()
        req = json.loads(raw)
        method = req.get("method", "")
        params = req.get("params", {})
        req_id = req.get("id")
        if method not in METHODS:
            result = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": req_id}
        else:
            try:
                ret = await METHODS[method](**params)
                result = {"jsonrpc": "2.0", "result": ret, "id": req_id}
            except Exception as exc:
                result = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(exc)}, "id": req_id}
        writer.write(json.dumps(result).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()
```

**Métodos JSON-RPC recomendados:**

| Método | Parámetros | Respuesta |
|--------|-----------|-----------|
| `ask` | `instruction: str` | `{plan: str, pending_id: str \| null, outcome: str}` |
| `confirm` | `pending_id: str, response: str` | `{accepted: bool, execution_id: str \| null}` |
| `status` | — | `{daemon_version: str, hermes_up: bool, pending_count: int}` |
| `audit` | `since: str \| null, limit: int` | `{events: list}` |

### Pattern 3: MCP Server con FastMCP (streamable HTTP, gateado)

**What:** FastMCP expone las herramientas de Wyss a Hermes. Cada tool handler pasa por `CognitivePolicyEngine` + audit.
**When to use:** D-59 — el MCP server hostea la única superficie de acción de Hermes.

```python
# Source: FastMCP docs (gofastmcp.com/deployment/http) — [VERIFIED: FastMCP official docs]
from fastmcp import FastMCP

mcp = FastMCP("wyss-tools")

@mcp.tool()
async def knowledge_query(query: str, kb_id: str | None = None) -> str:
    """Consulta el índice de conocimiento. Nivel A — ejecuta directo."""
    # Esta tool es siempre nivel A — no requiere plan completo
    subject = Subject(subject_id="hermes", subject_type=ActorType.ORCHESTRATOR)
    result = await retrieval.search(Query(query, kb_ids, 10), subject)
    audit.log(AuditEvent.new(...))
    return format_hits(result.hits)

@mcp.tool()
async def execute_plan(plan_json: str) -> str:
    """Evalúa y despacha un Plan propuesto por Hermes (D-51). Fail-closed."""
    plan = Plan(**json.loads(plan_json))  # deserializar
    decision = engine.evaluate(plan)
    audit.log(AuditEvent.new(event_type=AuditEventType.POLICY_DECISION, ...))
    if decision.outcome == Outcome.REJECT:
        return f"REJECTED: {decision.reasons}"
    if decision.outcome in (Outcome.CONFIRM_SIMPLE, Outcome.CONFIRM_STRONG):
        pending_id = pending_store.save(plan, decision, ttl_seconds=...)
        return f"PENDING:{pending_id}"
    # EXECUTE: encolar (Fase 6 ejecuta)
    execution_id = dispatch_queue.enqueue(plan, decision)
    return f"QUEUED:{execution_id}"

# Arrancar el servidor MCP en el daemon startup
def start_mcp_server(host: str = "127.0.0.1", port: int = 7420) -> None:
    mcp.run(transport="http", host=host, port=port)
    # Accesible en http://127.0.0.1:7420/mcp
```

**Configuración Hermes (docker-compose de Hermes):**
```yaml
# ~/.hermes/config.yaml montado en el container
agent:
  disabled_toolsets:
    - memory
    - web
    - code
    - filesystem  # TODOS los built-in tools off — Hermes solo usa MCP

mcp_servers:
  wyss:
    url: "http://host.docker.internal:7420/mcp"
    tools:
      include:
        - knowledge_query
        - execute_plan
        - get_status
```

**Docker Compose (prerequisito documentado, fuera del código Python):**
```yaml
services:
  hermes:
    image: ghcr.io/nousresearch/hermes-agent:latest
    extra_hosts:
      - "host.docker.internal:host-gateway"  # alcanza 127.0.0.1 del host
    volumes:
      - ~/.hermes:/root/.hermes
    environment:
      - HERMES_CONFIG=/root/.hermes/config.yaml
```

### Pattern 4: SQLite pending_proposals (schema recomendado)

**What:** Tabla append-friendly con estado y TTL para el flujo B/C.
**When to use:** D-54..D-57 — fuente de verdad de confirmaciones pendientes.

```sql
-- Source: ASSUMED (diseño propio basado en patrón audit_events existente)
CREATE TABLE IF NOT EXISTS pending_proposals (
    id           TEXT PRIMARY KEY,           -- pending_id (uuid4 hex)
    task_id      TEXT NOT NULL,              -- correlación con audit_events
    plan_json    TEXT NOT NULL,              -- Plan serializado
    risk_level   TEXT NOT NULL,             -- 'B' o 'C'
    outcome      TEXT NOT NULL,             -- 'CONFIRM_SIMPLE' o 'CONFIRM_STRONG'
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|confirmed|rejected|expired
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,             -- ISO8601 UTC; TTL configurable
    resolved_at  TEXT,                      -- NULL hasta resolución
    resolved_by  TEXT                       -- 'owner' | 'ttl_reaper'
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_proposals(status, expires_at);
```

**Pragmas (idénticos a audit.py — WAL fail-fast sobre NTFS):**
```python
PENDING_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",   # pendientes: NORMAL OK (no audit-critical)
    "PRAGMA busy_timeout=5000",
)
```

**TTL Reaper (asyncio background task):**
```python
# Source: ASSUMED — patrón asyncio background loop
async def ttl_reaper(pending_store: PendingStore, audit: AuditPort, interval_s: float = 30) -> None:
    while True:
        expired = pending_store.expire_old()   # UPDATE status='expired' WHERE expires_at < now()
        for proposal in expired:
            audit.log(AuditEvent.new(
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="propuesta expirada por TTL — auto-rechazada",
                payload={"pending_id": proposal.id, "risk_level": proposal.risk_level},
            ))
        await asyncio.sleep(interval_s)
```

**TTL recomendados por nivel:**
- Nivel B: 3600 segundos (1 hora)
- Nivel C: 900 segundos (15 minutos) — más destructivo, ventana más corta

### Pattern 5: OrchestratorPort — contrato hexagonal

**What:** Protocol que `HermesOrchestrator` implementa; el daemon lo invoca sin conocer a Hermes directamente.
**When to use:** D-58, D-60 — aísla Hermes del daemon core.

```python
# Source: ASSUMED — patrón establecido en core/ports/
# Archivo: src/core/ports/orchestrator.py
from typing import Protocol
from core.domain.plan import Plan
from core.orchestrator.intent import IntentClassification

class OrchestratorPort(Protocol):
    """Adapter del cerebro de orquestación. Hermes es la implementación concreta."""

    async def classify_intent(self, instruction: str) -> IntentClassification:
        """NL → IntentClassification (9 categories, ORCH-03). Hermes down → degradación D-60."""
        ...

    async def draft_plan(self, instruction: str, intent: IntentClassification) -> Plan:
        """Genera un Plan estructurado (D-51). El nivel lo asigna el engine, no este método."""
        ...

    async def health_check(self) -> bool:
        """True si Hermes está disponible. False → degradación explícita (D-60)."""
        ...
```

**Degradación D-60:**
```python
# En DaemonDispatcher.handle_ask():
if not await orchestrator.health_check():
    return {
        "outcome": "degraded",
        "message": "Orquestador Hermes no disponible. Consultas de conocimiento siguen activas.",
        "fallback_available": True
    }
```

### Pattern 6: Plan schema extension (D-62)

**What:** Extender `Action` con `on_error` y backoff — schema only, sin enforcement en Fase 5.
**When to use:** ORCH-07, D-62.

```python
# Extender src/core/domain/plan.py
from dataclasses import dataclass, field
from core.domain.risk import RiskLevel
from enum import StrEnum

class ErrorPolicy(StrEnum):
    RETRY    = "retry"
    ESCALATE = "escalate"
    ABORT    = "abort"

@dataclass(frozen=True, slots=True)
class RetryParams:
    max_attempts: int = 3
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0

@dataclass(frozen=True, slots=True)
class Action:
    type: str
    target: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.ABORT       # D-62 — Fase 6 lo ejecuta
    retry_params: RetryParams | None = None         # Solo relevante si on_error=RETRY

@dataclass(frozen=True, slots=True)
class Plan:
    task_id: str
    summary: str
    steps: tuple[Action, ...]
    rationale: str
    estimated_risk: RiskLevel | None = None
```

**Nota crítica:** Cambiar `Action` de frozen dataclass requiere verificar compatibilidad con los tests existentes (286 tests pasan actualmente). `on_error` con default `ErrorPolicy.ABORT` es retro-compatible con constructores existentes.

### Pattern 7: Golden eval POL-06 (D-63)

**What:** Test file con 20+ fixtures `NL_instruction → expected_level`; un falso-A rompe el build.
**When to use:** CI gate para POL-06 — replicar el patrón de `tests/policy/test_golden_plans.py`.

```python
# tests/policy/test_golden_nl_plans.py
# Source: src/tests/policy/test_golden_plans.py (patrón establecido en Fase 4)

@dataclass(frozen=True)
class NLGolden:
    instruction: str
    intent: str  # categoria esperada de ORCH-03
    expected_level: RiskLevel

# 20+ fixtures cubriendo A/B/C/D + ambiguos
NL_GOLDEN_CASES = (
    NLGolden("buscá mis apuntes de redes", "knowledge_query", RiskLevel.A),
    NLGolden("mové el archivo tesis.pdf a Documentos/", "file_operation", RiskLevel.B),
    NLGolden("borrá los logs de /tmp/wyss de hace más de 30 días", "file_operation", RiskLevel.C),
    NLGolden("formateá el disco /dev/sda1", "dangerous_operation", RiskLevel.D),
    NLGolden("hacé algo con mis archivos", "ambiguous_request", RiskLevel.A),  # clarification, no plan
    # ... ≥20 total
)

@pytest.mark.parametrize("case", NL_GOLDEN_CASES, ids=lambda c: c.instruction[:40])
def test_nl_golden_plan_level(case: NLGolden, engine: CognitivePolicyEngine) -> None:
    """Gate anti-falso-A: mide el engine determinístico, NO a Hermes (D-53, D-63)."""
    # El plan se construye desde la instrucción NL usando el mapper determinístico
    plan = nl_to_plan_fixture(case.instruction, case.intent)
    decision = engine.evaluate(plan)
    falso_a = " — FALSO-A CATASTRÓFICO: ejecutaría sin confirmar"
    assert decision.risk_level == case.expected_level, (
        f"{case.instruction!r}: esperado {case.expected_level.name}, "
        f"obtuvo {decision.risk_level.name}"
        + (falso_a if decision.risk_level < case.expected_level else "")
    )
```

**Patrón `nl_to_plan_fixture`:** función determinística que convierte `(instruction, intent)` → `Plan` con `Action`s predefinidas para cada categoria. Esto mide el engine (determinístico), no a Hermes (no determinístico). Hermes está DOWN durante estos tests — los fixtures son Plan objects construidos manualmente.

### Pattern 8: systemd user unit (D-61)

```ini
# ~/.config/systemd/user/wyss.service
# Source: ASSUMED — patrón estándar systemd user service
[Unit]
Description=Wyss Daemon
After=default.target

[Service]
Type=simple
ExecStart=/mnt/hdd/Data/10_Workspace/projects/wyss/.venv/bin/wyss start --config %h/.config/wyss/config.toml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

```bash
# Instalar y arrancar
systemctl --user daemon-reload
systemctl --user enable --now wyss.service
journalctl --user -u wyss.service -f
```

### Anti-Patterns to Avoid

- **FastAPI/HTTP para el IPC CLI:** Surface innecesaria, dep extra. El JSON-RPC sobre Unix socket es suficiente y más simple.
- **Bloquear el event loop en evaluación de política:** El engine es puro (sin IO) y rápido; no es async, no hace esperas. Llamar síncronamente desde el handler asyncio es correcto.
- **`evaluate_action()` público en el engine:** Anti-bypass por composición — el engine solo expone `evaluate(plan)` (ya implementado, no tocar).
- **Hermes clasificando el nivel A/B/C/D:** Viola D-50/D-53. El adapter solo trae el Plan; el engine asigna el nivel.
- **Unix socket para el MCP server:** El container Docker no puede alcanzar el Unix socket del host sin volumen mount explícito y configuración especial; TCP local es más simple y seguro.
- **Esperar respuesta de Hermes bloqueando el socket IPC:** `wyss ask` debe responder inmediatamente con el `pending_id`; Hermes trabaja en background. El patrón es fire-and-async, no blocking RPC.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP server tool registration y HTTP transport | Implementación manual del protocolo MCP | `fastmcp` (2.x) con `@mcp.tool()` + `mcp.run(transport="http")` | El protocolo MCP tiene sutilezas de session management y capability negotiation |
| Intent classification (NL → 9 categorías) | Regex / rule-based classifier | Hermes via `OrchestratorPort` | Hermes es un LLM entrenado para function calling; regex no escala a NL |
| Plan generation desde NL | Template-based planner | Hermes via `OrchestratorPort.draft_plan()` | El LLM entiende NL; el engine determinístico valida el resultado |
| Policy enforcement | Reglas ad-hoc per-command | `CognitivePolicyEngine.evaluate(plan)` (existente) | Ya implementado, testeado con 286 tests |

**Key insight:** La arquitectura híbrida Hermes+engine determinístico permite no construir un clasificador NL de cero (complejo) ni confiar el nivel de riesgo al LLM (inseguro). Cada componente hace lo que hace bien.

---

## Common Pitfalls

### Pitfall 1: Socket huérfano bloquea el arranque

**What goes wrong:** Si el daemon muere (SIGKILL, crash), el socket file queda en disco. El próximo `wyss start` falla con `OSError: [Errno 98] Address already in use`.
**Why it happens:** `asyncio.start_unix_server` no limpia el archivo automáticamente en Python 3.12 (en 3.13+ hay `cleanup_socket=True`).
**How to avoid:** Implementar `_cleanup_stale_socket()` que intenta conectar al socket existente; si la conexión es rechazada (proceso muerto), hacer `unlink` antes de bind.
**Warning signs:** `OSError: Address already in use` en el log del daemon al arrancar.

### Pitfall 2: Hermes llama MCP tools sin pasar por el engine

**What goes wrong:** Si el MCP server registra tools que ejecutan directamente sin pasar por `engine.evaluate()`, el contrato de fail-closed se rompe.
**Why it happens:** FastMCP con `@mcp.tool()` puede parecer un decorator inocente; es tentador hacer lógica directa dentro.
**How to avoid:** Cada tool handler en `mcp_server.py` DEBE: (1) construir un `Plan` de un solo `Action`, (2) llamar `engine.evaluate(plan)`, (3) ramificar por outcome. No hay atajo.
**Warning signs:** Tests de MCP tools que no tienen `engine` como dependency.

### Pitfall 3: Action frozen dataclass incompatibilidad

**What goes wrong:** Agregar `on_error` a `Action` con `field(default=...)` en un `frozen=True, slots=True` dataclass puede romper si algún test construye `Action` con args posicionales.
**Why it happens:** `slots=True` en Python 3.12 prohíbe agregar atributos después de la definición; los defaults nuevos cambian el orden de parámetros.
**How to avoid:** Agregar `on_error` y `retry_params` al FINAL de la definición con defaults. Buscar todos los `Action(...)` con args posicionales en el codebase antes de modificar.
**Warning signs:** `TypeError: __init__() takes N positional arguments` en tests existentes.

### Pitfall 4: WAL sobre NTFS para pending_proposals

**What goes wrong:** La `pending_proposals.db` abierta con WAL sobre `/mnt/hdd/Data/` (NTFS) puede fallar silenciosamente (mismo pitfall que audit.db).
**Why it happens:** NTFS/fuseblk puede no soportar WAL. El logger de audit ya hace fail-fast; `pending_store` debe hacer lo mismo.
**How to avoid:** Abrir con `PRAGMA journal_mode=WAL` y verificar el resultado como hace `SqliteAuditLogger`. Ubicar la DB en `data/` bajo el proyecto (ext4/SSD), no en `~/Data/` (NTFS).
**Warning signs:** La DB cae a journal mode sin error visible.

### Pitfall 5: Hermes container no alcanza el MCP server del host

**What goes wrong:** `http://localhost:7420/mcp` desde el container da `Connection refused` porque `localhost` dentro del container es el container, no el host.
**Why it happens:** Docker container networking — `localhost` es el loopback del container.
**How to avoid:** Usar `--add-host=host.docker.internal:host-gateway` en el compose de Hermes + configurar `url: "http://host.docker.internal:7420/mcp"` en el config de Hermes.
**Warning signs:** Hermes reporta "MCP server unreachable" en logs.

### Pitfall 6: Falso-A en POL-06 no bloquea el CI

**What goes wrong:** El test golden no diferencia `expected < actual` (sub-clasificación) de `actual < expected` (sobre-clasificación / falso-A). Un falso-A (esperado D, obtuvo A) es catastrófico.
**Why it happens:** `assert decision.risk_level == case.expected` falla en ambas direcciones por igual, pero el mensaje no enfatiza el falso-A.
**How to avoid:** Replicar el patrón exacto de `test_golden_plans.py` que incluye el literal `" — FALSO-A"` en el mensaje de assert cuando `decision.risk_level < case.expected`.

### Pitfall 7: `wyss confirm` bloqueante en ejecución

**What goes wrong:** Si `confirm` espera a que la acción se ejecute, el CLI queda colgado y el daemon no puede atender otras conexiones.
**Why it happens:** Mezclar la capa de confirmación con la capa de ejecución.
**How to avoid:** D-57 — `confirm` solo encola en la dispatch queue y responde inmediatamente con `execution-id`. La ejecución real es Fase 6.

---

## Code Examples

### Async JSON-RPC handler completo

```python
# Source: ASSUMED — patrón asyncio streams (docs.python.org/3/library/asyncio-stream.html)
import asyncio
import json
from typing import Any

class DaemonServer:
    def __init__(self, engine, orchestrator, pending_store, audit, retrieval):
        self._engine = engine
        self._orchestrator = orchestrator
        self._pending_store = pending_store
        self._audit = audit
        self._retrieval = retrieval

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            req = json.loads(line)
            resp = await self._dispatch(req)
            writer.write(json.dumps(resp).encode() + b"\n")
            await writer.drain()
        except json.JSONDecodeError:
            error = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
            writer.write(json.dumps(error).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, req: dict) -> dict:
        method = req.get("method", "")
        params = req.get("params", {})
        rid = req.get("id")
        handlers = {
            "ask": self._handle_ask,
            "confirm": self._handle_confirm,
            "status": self._handle_status,
            "audit": self._handle_audit,
        }
        if method not in handlers:
            return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": rid}
        try:
            result = await handlers[method](**params)
            return {"jsonrpc": "2.0", "result": result, "id": rid}
        except Exception as exc:
            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(exc)}, "id": rid}
```

### CLI client (`wyss ask`)

```python
# Añadir a src/bootstrap/cli.py — Source: ASSUMED patrón asyncio Unix client
@app.command()
def ask(
    instruction: str,
    config: Path = Path("config/config.toml"),
) -> None:
    """Envía instrucción al daemon activo (ORCH-02)."""
    settings = load_settings(config)
    socket_path = settings.data_dir / "wyss.sock"

    async def _ask() -> dict:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
        except FileNotFoundError:
            console.print("Daemon no está corriendo. Usar: wyss start", style="red")
            raise typer.Exit(1)
        try:
            req = json.dumps({"jsonrpc": "2.0", "method": "ask", "params": {"instruction": instruction}, "id": 1})
            writer.write(req.encode() + b"\n")
            await writer.drain()
            resp = json.loads(await reader.readline())
            return resp.get("result", {})
        finally:
            writer.close()
            await writer.wait_closed()

    result = asyncio.run(_ask())
    _render_ask_result(result)
```

### HermesOrchestrator adapter

```python
# Source: ASSUMED — sigue el patrón de ModelGateway (httpx async)
import httpx
import json
from core.domain.plan import Action, Plan, ErrorPolicy
from core.orchestrator.intent import IntentClassification, IntentCategory
from core.ports.orchestrator import OrchestratorPort

class HermesOrchestrator:
    """Adapter que implementa OrchestratorPort usando la API de Hermes Agent."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self._api_key = api_key
        self._model = model

    async def classify_intent(self, instruction: str) -> IntentClassification:
        """Llama a Hermes vía OpenAI-compatible API para clasificar la intención."""
        try:
            resp = await self._client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                        {"role": "user", "content": instruction},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = json.loads(data["choices"][0]["message"]["content"])
            return IntentClassification(
                category=IntentCategory(content["category"]),
                confidence=content.get("confidence", 0.0),
                clarification_needed=content.get("ambiguous", False),
            )
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
            # D-60: degradación explícita, no excepción
            raise OrchestratorUnavailable(f"Hermes no disponible: {exc}") from exc

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/v1/models", timeout=2.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE transport en MCP | Streamable HTTP (`/mcp` endpoint) | 2025 (MCP spec update) | SSE deprecado; usar `transport="http"` en FastMCP |
| `python-daemon` (PEP 3143) para daemons | systemd user units | 2020+ (systemd universal) | `python-daemon` obsoleto en entornos con systemd |
| LangChain/LlamaIndex para orquestación NL | Agente LLM con tool calling estructurado | 2024-2025 | Los frameworks de orquestación pelean contra la arquitectura hexagonal propia |
| asyncio `loop.create_unix_server()` | `asyncio.start_unix_server()` (streams API) | Python 3.10+ | La streams API es más idiomática |
| `asyncio.start_unix_server(cleanup_socket=False)` | `cleanup_socket=True` disponible en Python 3.13 | Python 3.13 | En 3.12 (este proyecto), hacer cleanup manual |
| FastMCP 3.x (nueva API breaking) | FastMCP 2.14.x (API estable) | 2025 | La versión 3.x cambia la API; pin a 2.14.x |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `fastmcp>=2.14,<3` tiene API estable de `mcp.run(transport="http", host=, port=)` | Standard Stack, Pattern 3 | Si la API cambió, reescribir el MCP server startup |
| A2 | `ghcr.io/nousresearch/hermes-agent:latest` es la imagen Docker oficial de Hermes Agent | Pattern 3 (Docker Compose) | Si la imagen está en otro registry, actualizar el compose |
| A3 | Hermes Agent v0.16.0 soporta `disabled_toolsets: [memory, web, code, filesystem]` (o equivalente) para deshabilitar todos los built-in tools | Pattern 3 (Hermes config) | Si las keys exactas difieren, ajustar config YAML |
| A4 | `http://host.docker.internal:7420/mcp` con `--add-host=host.docker.internal:host-gateway` funciona en Docker Linux (CachyOS) | Pattern 3 (Docker networking) | En algunas configs de Docker Linux, `host-gateway` no está disponible; fallback: `host_ip` fijo o `network_mode: host` |
| A5 | Schema de `pending_proposals` con columnas propuestas es compatible con los PRAGMAs WAL sobre el filesystem del proyecto (ext4 SSD) | Pattern 4 | Si la DB está en NTFS, WAL falla — usar ext4 (ya documentado) |
| A6 | `Action.on_error` con default `ErrorPolicy.ABORT` es retro-compatible con los 286 tests existentes | Pattern 6 | Si algún test construye Action con args posicionales, fallará |
| A7 | TTL de 3600s (B) y 900s (C) son valores razonables para el owner | Pattern 4 | Ajustar si el owner prefiere ventanas distintas |

---

## Open Questions

1. **Imagen Docker de Hermes Agent**
   - What we know: Hermes Agent tiene Docker Compose oficial en el repo NousResearch/hermes-agent
   - What's unclear: El nombre exacto de la imagen Docker publicada (`ghcr.io/nousresearch/hermes-agent` no verificado)
   - Recommendation: En Wave 0 del plan, verificar `docker pull ghcr.io/nousresearch/hermes-agent:latest` y confirmar la imagen correcta antes de escribir el compose

2. **Modelo LLM para Hermes en este setup**
   - What we know: Hermes soporta 100+ proveedores vía config.yaml; el owner tiene LiteLLM en localhost:4000 con Gemini+Qwen+DeepSeek
   - What's unclear: Qué modelo usar dentro del container Hermes para clasificar intenciones de Wyss (routing: LiteLLM como proxy o Nous Portal)
   - Recommendation: Configurar `model.base_url: "http://host.docker.internal:4000/v1"` para que Hermes use LiteLLM del owner (Gemini para clasificación de intención = "acarreo")

3. **FastMCP 2.x vs 3.x API**
   - What we know: FastMCP 3.4.2 está en PyPI; la versión 3.x tiene breaking changes respecto a 2.x
   - What's unclear: Si el API de `mcp.run(transport="http", host=..., port=...)` existe igual en 2.14.x
   - Recommendation: Verificar `uv add "fastmcp>=2.14,<3" && python -c "from fastmcp import FastMCP; help(FastMCP.run)"` en Wave 0

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Daemon runtime | Yes | 3.12.13 | — |
| Docker | Hermes container | Yes | 29.5.2 | — |
| Docker Compose | Hermes orchestration | Yes | 5.1.4 | — |
| systemd user units | Daemon supervision (D-61) | Yes | Running | — |
| `uv` | Dep management | Yes | latest | — |
| LiteLLM (localhost:4000) | Hermes model backend (recomendado) | Assumed running | — | Nous Portal / OpenRouter directo |

**Missing dependencies with no fallback:** None — todo disponible.

**Missing dependencies with fallback:**
- LiteLLM: si está down, Hermes puede usar otro provider directo (Nous Portal). No bloquea.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x con `asyncio_mode="auto"` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/orchestrator/ tests/policy/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-01 | daemon arranca, crea socket, responde ping | integration | `pytest tests/orchestrator/test_daemon.py -x` | No — Wave 0 |
| ORCH-01 | socket huérfano limpiado al arrancar | unit | `pytest tests/orchestrator/test_daemon.py::test_stale_socket_cleanup -x` | No — Wave 0 |
| ORCH-02 | `wyss ask` envía al daemon y recibe respuesta | integration | `pytest tests/orchestrator/test_daemon.py::test_ask_round_trip -x` | No — Wave 0 |
| ORCH-03 | Intent clasificado en ≥9 categorías (fake orchestrator) | unit | `pytest tests/orchestrator/test_intent_router.py -x` | No — Wave 0 |
| ORCH-04 | Instrucción ambigua devuelve `clarification_needed=True` | unit | `pytest tests/orchestrator/test_intent_router.py::test_ambiguous -x` | No — Wave 0 |
| ORCH-05 | Plan legible generado para tarea modificadora | unit | `pytest tests/orchestrator/test_plan_renderer.py -x` | No — Wave 0 |
| ORCH-06 | pending_proposals sobrevive restart (WAL + reload) | unit | `pytest tests/orchestrator/test_pending_store.py -x` | No — Wave 0 |
| ORCH-07 | `Action.on_error` serializa y deserializa correctamente | unit | `pytest tests/domain/test_plan.py -x` | No — Wave 0 |
| POL-06 | ≥20 fixtures NL→nivel; falso-A rompe build | unit (golden gate) | `pytest tests/policy/test_golden_nl_plans.py -x` | No — Wave 0 |
| AUD-02 | `wyss audit` lista eventos de una sesión | integration | `pytest tests/orchestrator/test_audit_query.py -x` | No — Wave 0 |
| — | Existing 286 tests siguen verdes tras Action schema change | regression | `uv run pytest tests/ -q` | Yes |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/orchestrator/ tests/policy/ -x -q && uv run mypy src/orchestrator/ src/core/ports/orchestrator.py && uv run ruff check src/orchestrator/ && uv run lint-imports`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green + `test_golden_nl_plans.py` green (0 falsos-A)

### Wave 0 Gaps

- [ ] `tests/orchestrator/__init__.py`
- [ ] `tests/orchestrator/conftest.py` — fixtures: `engine`, `fake_orchestrator`, `pending_store`, `daemon_client`
- [ ] `tests/orchestrator/test_daemon.py` — cubre ORCH-01, ORCH-02
- [ ] `tests/orchestrator/test_intent_router.py` — cubre ORCH-03, ORCH-04
- [ ] `tests/orchestrator/test_pending_store.py` — cubre ORCH-06 (WAL, TTL, ordering)
- [ ] `tests/orchestrator/test_plan_renderer.py` — cubre ORCH-05
- [ ] `tests/orchestrator/test_audit_query.py` — cubre AUD-02
- [ ] `tests/domain/test_plan.py` — extender con ORCH-07 (on_error schema)
- [ ] `tests/policy/test_golden_nl_plans.py` — cubre POL-06 (≥20 fixtures, falso-A gate)
- [ ] Framework install: `uv add "mcp>=1.27,<2" "fastmcp>=2.14,<3"` — si no instalado

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (local daemon, single-owner) | Unix socket = solo procesos locales del owner |
| V3 Session Management | No | No hay sessions HTTP en el IPC |
| V4 Access Control | Yes | OrchestratorPort fail-closed; MCP tools requieren plan + engine |
| V5 Input Validation | Yes | `instruction` NL sanitizado antes de enviar a Hermes (ContextMinimizer existente) |
| V6 Cryptography | No | No hay crypto nueva; audit WAL es durabilidad, no cifrado |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via NL instruction | Tampering | ContextMinimizer filtra secretos; NL es dato, no instrucción de sistema |
| Hermes propone nivel A para acción destructiva (bypass) | Elevation of Privilege | D-50: engine determinístico asigna el nivel, Hermes no puede bajarlo |
| MCP tool call que saltea el engine | Elevation of Privilege | Cada `@mcp.tool()` handler DEBE llamar `engine.evaluate()` — verificado en tests |
| pending_proposal confirmada después de expirar | Tampering | TTL reaper marca `status=expired` antes; `confirm` rechaza proposals no `pending` |
| Socket Unix accesible por otros usuarios | Spoofing | Permisos 0600 en el socket file; `os.chmod(socket_path, 0o600)` al crear |
| Acción D enviada via JSON-RPC directo (bypass de Hermes) | Elevation of Privilege | `engine.evaluate()` es el único gate; el daemon lo llama siempre sin excepción |

---

## Sources

### Primary (HIGH confidence)

- Codebase wyss/src/core/ — engine.py, plan.py, risk.py, policy.py, audit/schema.py, audit/sqlite_logger.py leídos directamente
- Codebase wyss/tests/policy/test_golden_plans.py — patrón golden gate leído directamente
- docs/18-prompt-implementacion.md — reglas inviolables 1-9, arquitectura hexagonal
- docs/13-politica-acceso-seguridad.md — niveles A/B/C/D, fail-closed
- 05-CONTEXT.md — decisiones locked D-50..D-63
- FastMCP docs (gofastmcp.com/deployment/http) — streamable HTTP transport pattern [VERIFIED: oficial]
- Hermes Agent MCP config ref (github.com/NousResearch/hermes-agent/docs/reference/mcp-config-reference.md) — `mcp_servers:`, `disabled_toolsets:` [VERIFIED: oficial]
- Python asyncio docs — `start_unix_server`, streams API [VERIFIED: docs.python.org]
- PyPI registry — mcp 1.27.2, fastmcp disponible en 2.x y 3.x [VERIFIED: pip index versions]

### Secondary (MEDIUM confidence)

- gofastmcp.com — FastMCP HTTP deployment pattern, Docker container connection via `host.docker.internal`
- hermes-agent.nousresearch.com — configuración de providers, api-server endpoints, MCP integration
- NousResearch/Hermes-Function-Calling GitHub — ChatML tool calling format, `<tool_call>` tags

### Tertiary (LOW confidence / ASSUMED)

- Docker `--add-host=host.docker.internal:host-gateway` disponibilidad en CachyOS Linux — no verificado empíricamente en este entorno
- Imagen Docker `ghcr.io/nousresearch/hermes-agent:latest` — nombre no verificado contra registry

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versiones verificadas contra PyPI, packages slopcheck OK
- Architecture: HIGH — patrón hexagonal existente + código leído directamente
- Hermes integration: MEDIUM — API documentación verificada pero no ejecutada E2E
- MCP transport: MEDIUM — FastMCP docs verificados; Docker networking [ASSUMED] en CachyOS
- Pitfalls: HIGH — mayoría verificados contra el código existente o CPython issues

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (FastMCP y Hermes Agent están en desarrollo activo — re-verificar versiones antes de instalar)
