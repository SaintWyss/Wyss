# Architecture

Hexagonal enforced por `import-linter` (2 contratos en pyproject, la cadena de verificación los corre):

1. **`core` es puro** — stdlib only; no importa pydantic ni ninguna capa.
2. **Las capas son independientes** — `orchestrator, agents, knowledge, gateway, execution, audit, ledger`
   solo importan de `core`, jamás entre sí. Todo cableado cruzado se inyecta por constructor desde
   `bootstrap` (composition root, única frontera Pydantic).

```
bootstrap (CLI Typer + config Pydantic→frozen + DI manual)
   └─ orchestrator (daemon Unix-socket JSON-RPC, dispatcher fail-closed, PendingStore B/C,
                    LLMOrchestrator — adapter de OrchestratorPort que recibe ModelGatewayPort inyectado)
        └─ core/policy (CognitivePolicyEngine: Plan → PolicyDecision A/B/C/D; BUILTIN_DENY Final,
                        la config solo AGREGA reglas) → execution (PlanExecutor → FileSystem/Shell/Git,
                        segunda muralla D-68, UndoJournal, verify post-acción)
   agents (ConfiguredAgent config-driven [[agents]], ScopedRetrieval, anti-injection)
   knowledge (ingesta secret-gated → FTS5+Chroma → retrieval RRF)
   gateway (única salida a modelos: cost gate PRE-llamada, minimizer, providers, traces)
   audit (append-only, DB separada) — transversal: todo el camino queda registrado
   ledger (finanzas: agregaciones SQL deterministas, nunca LLM para números)
```

Detalle completo: `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` (capas, flujos, anti-patterns)
y `docs/audit/WYSS_SYSTEM_MAP.md` (mapa por archivo).

**Protegidos D-85** — no tocar sin decisión explícita del owner: `src/gateway/cost.py`,
`src/gateway/gateway.py`, `src/orchestrator/dispatcher.py`, `src/agents/configured_agent.py`,
`src/agents/registry.py`. Tampoco vaciar/perforar `src/core/policy/builtin_deny.py`.

Reglas duras que ningún cambio puede violar: el LLM solo propone (el nivel A-D lo asigna el engine
determinístico; `estimated_risk` solo puede subir — POL-04); jamás `shell=True` (test AST lo enforcea);
`shutil.move` y no `os.rename` (EXDEV cross-FS NTFS↔ext4); errores de adapters son resultados
(`ToolResult(success=False)`), no excepciones propagadas.
