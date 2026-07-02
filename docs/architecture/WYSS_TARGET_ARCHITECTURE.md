# Wyss — Target Architecture

> 2026-07-02. Principio rector de este documento: **la target architecture ES la actual**.
> La arquitectura hexagonal implementada y enforced (import-linter) es correcta; este doc la
> formaliza (CLAUDE.md decía "Architecture not yet mapped") y define solo lo que FALTA.

## 1. Forma general (se mantiene)

```
OWNER
 └─ bootstrap/ (composition root, única frontera Pydantic, DI manual)
     └─ CLI Typer  ──►  orchestrator/ daemon (Unix socket JSON-RPC)
                              │
              ┌───────────────┼────────────────────┐
              ▼               ▼                    ▼
        core/policy      core/orchestrator     PendingStore B/C
        (A-D, DENY)      (intent puro)         (confirmaciones + TTL)
              │
              ▼
        execution/ (PlanExecutor → FileSystem/Shell/Git adapters,
                    2da muralla + UndoJournal + verify)
              │
        audit/ (append-only, DB separada)  ◄── TODO el camino

        agents/ (ConfiguredAgent config-driven, ScopedRetrieval, anti-injection)
        knowledge/ (ingesta secret-gated → FTS5+Chroma → RRF)
        gateway/ (cost gate pre-llamada, minimizer, providers)
        ledger/ (dominio finanzas)
```

## 2. Responsabilidades por capa (estado: implementado salvo lo marcado ⬜)

| Capa | Responsabilidad | Regla dura |
|---|---|---|
| `core/domain` | Entidades frozen, errores de dominio | stdlib only; no importa nada del sistema |
| `core/ports` | Contratos (Protocols + AgentBase) | Se modifican ANTES que cualquier impl (D-11) |
| `core/policy` | Plan → PolicyDecision; denylist D | `BUILTIN_DENY` es `Final`; config solo AGREGA |
| `orchestrator` | daemon, dispatch fail-closed, bandeja B/C | Nunca ejecuta sin PolicyDecision |
| `agents` | instanciación config-driven, permisos estructurales, memoria | Cero código por agente nuevo (D-73); retrieved = untrusted |
| `knowledge` | ingesta, índice híbrido, retrieval | Chunk con secreto jamás entra al índice (fail-closed) |
| `gateway` | única salida a modelos externos | Cost gate PRE-llamada; contexto mínimo; secretos fail-closed |
| `execution` | efectos sobre el entorno | 2da muralla; argv exec (jamás shell=True); todo con undo+verify |
| `audit` | registro transversal | append-only, DB separada de datos de usuario |
| `ledger` | dominio finanzas | agregaciones SQL deterministas (nunca LLM para números) |
| `bootstrap` | config+DI+CLI | Pydantic no cruza esta frontera |
| ⬜ **orquestador LLM** | convertir lenguaje natural en `Plan` vía `OrchestratorPort` | ver §3 — el único hueco arquitectónico real |

## 3. Capa AI/modelos — decisión pendiente y recomendación

**Estado**: `OrchestratorPort` existe; el daemon corre con orquestador determinístico; el adapter
planeado (Hermes local vía Docker+MCP, plan 05-05) está bloqueado por infraestructura externa.

**Recomendación (decisión a tomar por el owner, D-nueva):**

- Implementar **`LLMOrchestrator`**: adapter de `OrchestratorPort` que usa el **gateway existente**
  (providers `litellm`/`anthropic` ya escritos, cost gate y minimizer ya operativos) para producir un
  `Plan` estructurado a partir de la petición del owner.
- Contrato inviolable: el LLM **solo propone** `Plan`; la clasificación de riesgo la hace
  `CognitivePolicyEngine` determinístico (decisión existente: "el LLM solo puede subir riesgo, nunca bajarlo").
  Output del LLM parseado a dominio con validación estricta; parse fallido = plan rechazado (fail-closed).
- Hermes queda como **segundo adapter opcional** detrás del mismo port (local-first cuando haya imagen).
  Así el proyecto cumple su propio principio: "no depender de un modelo forever".

**Fallbacks**: router del gateway ya soporta tiers; orden recomendado litellm→anthropic→(ollama futuro).
**Contención de alucinación**: dominio tipado + policy determinístico + confirmación B/C = el plan
alucinado más dañino posible termina en bandeja de confirmación o rechazo D, nunca en ejecución directa.

## 4. Memoria

`AgentMemory` (D-71) ya define la regla correcta: persiste preferencias; solo el owner o extracción
supervisada escriben. No agregar memoria conversacional libre en v0.1 — es superficie de injection.

## 5. Automatización (fase 9 — diseño futuro, no construir aún)

Scheduler (APScheduler o systemd timers) SIEMPRE detrás del mismo embudo: rutina → Plan → policy →
bandeja B/C. Regla ya escrita en ROADMAP fase 9: acciones B/C de rutinas **jamás auto-ejecutadas**;
idempotencia por ventana. Nada de esto se construye antes de cerrar PR-06.

## 6. Configuración

Se mantiene: TOML sin secretos → Pydantic fail-fast → frozen. Faltantes a cerrar (PR-03):
`config/.env` real desde `.env.example`; documentar en README qué servicio provee cada key;
`config.example.toml` es el contrato público — cada key nueva entra primero ahí.

## 7. Errores

Patrón existente (mantener): errores de dominio en `core/domain/errors.py`; adapters capturan
internamente y devuelven resultados (`ToolResult(success=False)`, no excepciones propagadas — decisión
06-03); fail-closed en todo path de seguridad. Prohibido introducir `except Exception: pass`.

## 8. Testing

Se mantiene la pirámide actual: dominio/policy puros con golden tests; adapters contra recursos reales
en `tmp_path`; NTFS opt-in (`WYSS_TEST_NTFS=1`); fakes inyectados por ports; `llm_judge` opt-in.
Faltante: los tests NTFS deben escribir bajo `data/tmp_tests/` con cleanup (PR-00), y la cadena debe
correr en CI (PR-01).

## 9. Release

Faltante completo (PR-10): tag semver `v0.1.0-rc1`; criterio de RC = índice + búsqueda + ledger +
conversación LLM real calibrada + daemon bajo systemd user unit (`~/.config/systemd/user/wyss.service`,
prometido por STACK.md y nunca creado). Fase 10 (Modo Equipo) queda fuera de v0.1.

## 10. Anti-patterns (consolidación de decisiones ya tomadas — enforced donde se pudo)

1. **No LangChain/LlamaIndex** — pelean contra los ports propios (STACK.md).
2. **No FastAPI/HTTP para IPC** — Unix socket JSON-RPC ya decidido.
3. **No `shell=True`, jamás** — enforced por test AST (06-03).
4. **No vaciar/perforar la denylist D** — `Final` en código; config solo agrega.
5. **No ORM** — SQL directo auditable.
6. **No lógica de negocio en bootstrap** — composition root cablea, no decide.
7. **No números por LLM** — agregaciones del ledger son SQL determinista (D-87).
8. **No tocar protegidos D-85** (`cost.py`, `gateway.py`, `dispatcher.py`, `configured_agent.py`, `registry.py`) sin decisión explícita del owner.
9. **No `os.rename` donde va `shutil.move`** — EXDEV cross-FS NTFS↔ext4 (D-06-04, grep gate).
10. **No agregar deps sin consumidor** — lección fastmcp/mcp (PR-03).
