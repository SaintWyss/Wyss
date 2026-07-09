# Wyss v0.1 Release Candidate

**Fecha:** 2026-07-09 · **Estado:** RC cerrado — loop E2E verificado con LLM real.

## Qué puede hacer v0.1 RC

El loop de producto completo funciona de punta a punta:

```
ask → plan (LLM real vía gateway) → política A-D determinística → confirmación
→ ejecución (PlanExecutor) → verificación → auditoría → journal de undo
```

- `wyss index <ruta> --bc <nombre>` — indexa documentos (FTS5 + vectores; degrada a FTS-only si Ollama no está).
- `wyss search "<consulta>"` — búsqueda híbrida sobre las BC indexadas.
- `wyss fin add-ingreso/add-gasto/ver` — ledger de finanzas determinístico.
- `wyss start` — daemon Unix-socket con orquestador LLM real (`[orchestrator] mode = "llm"`) o determinístico (default).
- `wyss ask "<instrucción>"` — el LLM propone un plan tipado; el engine determinístico asigna nivel A-D (el LLM **nunca** decide riesgo).
- `wyss confirm <pending_id>` — nivel B exige `s`, nivel C exige `CONFIRMAR` literal; recién ahí el PlanExecutor ejecuta, verifica el resultado y audita `task.completed`/`task.failed`.
- `wyss audit` — evidencia completa: comando recibido, plan creado, decisión de política, confirmación pedida/respondida, costo del gateway, resultado de ejecución.
- Undo: cada mutación graba en `data/execution/journal.db` (`undo_entries`) la operación inversa (`inverse_op`) antes de mutar; ABORT hace rollback en orden inverso.
- `wyss web` — consola local (bridge HTTP 127.0.0.1 con token; nunca decide riesgo).

## Qué NO hace todavía

- `file.read`/`file.list` por el executor: no soportados — el resultado lo dice honesto (`success=false`, `task.failed` auditado). Lectura real = `wyss search`.
- Shell: allowlist **vacía** por default (fail-closed). Ningún binario corre hasta permitirlo por config.
- Git: adapter apunta al data_dir (sin repo → toda acción git falla como resultado).
- Targets de planes deben ser rutas absolutas ya resueltas: `~`, rutas relativas o symlinks los bloquea la segunda muralla como path-tricks (deuda conocida F3).
- Hermes: NO es dependencia. El orquestador real usa el gateway/LiteLLM existente; Hermes queda como adapter futuro opcional.
- `wyss undo` como comando no existe: el journal registra la evidencia y el rollback automático corre en ABORT; restore manual = fase siguiente.
- Multi-agente simultáneo, scheduler, rutinas (Fase 9/10): fuera de v0.1.

## Setup

```bash
uv sync
cp config/config.example.toml config/config.toml   # editar rutas/tiers
cp config/.env.example config/.env                 # completar claves
```

Variables de entorno (en `config/.env`, junto al config.toml que uses):

| Variable | Uso |
|---|---|
| `LITELLM_MASTER_KEY` | Bearer del proxy LiteLLM local (tier económico) |
| `LITELLM_BASE_URL` | Opcional; default `http://localhost:4000`. Acepta con o sin `/v1` |
| `ANTHROPIC_API_KEY` | Tier fuerte (opcional si no se usa) |

Orquestador LLM real: en `config.toml`:

```toml
[orchestrator]
mode = "llm"          # default: "deterministic"
tier = "economico"
```

## Tests y gates

```bash
uv run pytest -q            # 465 passed
uv run mypy                 # 0 issues
uv run ruff check src tests # limpio
uv run lint-imports         # 2 contratos kept
```

Loop E2E sin LLM (CI-safe): `uv run pytest tests/orchestrator/test_daemon_execution.py -q`.

## Smoke test manual (verificado 2026-07-09)

Sandbox controlado — jamás sobre datos reales:

```bash
mkdir -p ~/.wyss-smoke/{data,sandbox}
# config.toml de smoke: data_dir/audit_db absolutos bajo ~/.wyss-smoke/data + [orchestrator] mode="llm"
# .env de smoke junto a ese config.toml con LITELLM_MASTER_KEY

uv run wyss start --config ~/.wyss-smoke/config.toml &
uv run wyss ask "Creá un archivo en la ruta exacta /home/<user>/.wyss-smoke/sandbox/hola.txt con el contenido: hola desde Wyss RC. Ruta absoluta, sin ~." --config ~/.wyss-smoke/config.toml
# → Pending <id> · Nivel: C
uv run wyss confirm <id> --config ~/.wyss-smoke/config.toml   # escribe CONFIRMAR
# → Ejecutado (exec-…): plan completado (1 pasos)
cat ~/.wyss-smoke/sandbox/hola.txt                            # → hola desde Wyss RC.
uv run wyss audit --config ~/.wyss-smoke/config.toml          # cadena completa
```

Resultado real del smoke destructivo (qwen planificó `file.delete /etc/passwd`):

```
╭───────── Rechazado ──────────╮
│ denylist: system-files-write │
╰──────────────────────────────╯
```

## Modelo de seguridad

- **El LLM solo propone.** El nivel A-D lo asigna `CognitivePolicyEngine` determinístico; `estimated_risk` solo puede subir (POL-04).
- **Denylist D en código** (`builtin_deny.py`, Final) — la config solo agrega reglas, jamás las quita.
- **Confirmación**: B = `s`, C = `CONFIRMAR` literal; TTL con auto-reject. Al confirmar se **re-evalúa** el plan (si la política cambió, se rechaza).
- **Segunda muralla**: el FileSystemAdapter re-evalúa cada acción con path resuelto antes de cualquier I/O.
- **Journal antes de mutar**; borrado = send2trash, nunca unlink (D-64).
- **Auditoría append-only** en DB separada; nada relevante ocurre sin registro.
- Errores de adapters son resultados (`ToolResult(success=False)`), nunca excepciones que escapan.

## Limitaciones conocidas

- Gemini free-tier tira 429/503 con frecuencia; el gateway reintenta 2x transitorios y degrada fail-closed (`Error sistémico: orquestador LLM no disponible`). Cambiar de alias en `[gateway.tiers]` destraba.
- Un pedido que el LLM se niega a planificar (p. ej. destructivo) termina en `plan del LLM inválido` — fail-closed correcto, mensaje mejorable.
- `wyss audit` lee la DB directo; el método JSON-RPC `audit` del daemon devuelve vacío (deuda menor).
- El path pending audita la decisión de política dentro de `confirmation.requested` (payload), no como evento `policy.decision` separado.

## Mobile Bridge MVP (agregado 2026-07-09)

Wyss se controla desde el teléfono en la misma LAN: `wyss web --lan` imprime la
URL de pairing (token una vez → cookie), la SPA es responsive (bottom-nav móvil)
y el flujo completo ask → riesgo → CONFIRMAR → resultado → auditoría corre desde
el browser del teléfono contra el mismo daemon del PC. Sin `--lan` nada cambia
(127.0.0.1 only). Host allowlist exacta (solo el IP LAN de la máquina), 401 sin
auth en todo path. Detalle y smoke: `docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md`.

## Próxima fase recomendada

1. **PR-08 security re-audit** sobre el loop de ejecución ahora real (era el paso previo a RC en el roadmap).
2. `wyss undo <task_id>` como comando sobre el journal existente.
3. Soporte `file.read`/`file.list` en el executor + normalización expanduser en la segunda muralla (cierra deuda F3).
