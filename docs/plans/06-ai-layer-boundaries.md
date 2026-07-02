# PR-06 — LLMOrchestrator: conversación real detrás del policy engine

> **EJECUTADO 2026-07-02** (decisión F4 del owner: opción A — adapter vía gateway; Hermes queda como
> adapter opcional futuro). Construcción: Codex (`codex-gsd-exec`); verificación y commit: Claude.
> Desvío menor aceptado: `bootstrap.config` expone `WyssSettings` como subclase frozen del tipo de
> dominio (agrega `orchestrator`) para no tocar `core/domain` — Liskov-compatible, mypy strict OK.
> Gate: 435 passed / mypy 0 / ruff / import-linter 2/2 kept. **Pendiente §11 (verificación manual
> con LLM real): requiere config/.env + LiteLLM up — cierra junto con la calibración advisory (F6).**

## 1. Objective
Cablear el path conversacional del daemon con un LLM real: `wyss ask` → `LLMOrchestrator` (adapter de `OrchestratorPort` que usa el gateway existente) → `Plan` tipado → `CognitivePolicyEngine` → ejecución/bandeja/rechazo.

## 2. Context from the audit
Es el gap #1 del producto. El daemon, la política, los adapters y el gateway existen y están testeados; el orquestador conversacional planeado (Hermes local, plan 05-05) está BLOCKED por infraestructura externa (sin imagen Docker publicada, disabled_toolsets, UFW — ver `05-EMPIRICAL.md`). Mientras tanto `ask` corre contra `_DeterministicOrchestrator` fake. El gateway ya tiene providers `litellm` y `anthropic` escritos y testeados, cost gate pre-llamada y context minimizer.

**PRE-REQUISITO: decisión del owner (F4 del roadmap)** — este spec asume la recomendación del audit: adapter API vía gateway ahora; Hermes queda como segundo adapter futuro detrás del mismo port.

## 3. Exact problem
`OrchestratorPort` no tiene implementación real. El producto no puede hacer lo que su README promete: recibir una instrucción en lenguaje natural y convertirla en un plan ejecutable con juicio.

## 4. Architectural decision
- El LLM **solo propone** un `Plan`; jamás clasifica riesgo en forma vinculante (decisión existente: el LLM solo puede SUBIR riesgo). La clasificación la hace `CognitivePolicyEngine` determinístico.
- Salida del LLM → JSON estricto → parseo a dominio frozen con validación total; cualquier fallo de parseo/campo desconocido = plan rechazado fail-closed (patrón espejo de `_plan_from_json` en `daemon.py`).
- Toda llamada pasa por el gateway (cost gate + minimizer + traces). El orquestador NO llama providers directo.
- Cero cambios en los archivos protegidos D-85.

## 5. Files to read first
- `src/core/ports/orchestrator.py` (el contrato a implementar)
- `src/orchestrator/daemon.py` (cómo se inyecta el orquestador hoy; `_plan_from_json`, `_action_from_dict`)
- `src/orchestrator/dispatcher.py` (SOLO lectura — protegido)
- `src/core/orchestrator/intent.py` (clasificación de intención pura existente)
- `src/gateway/gateway.py` + `src/gateway/providers/litellm.py` (SOLO lectura — protegido; cómo se invoca)
- `src/bootstrap/gateway.py` y `src/bootstrap/cli.py` comandos `start`/`ask` (composition root)
- `src/agents/pellegrini.py` (patrón de construcción config-driven a imitar)
- `.planning/phases/05-orquestador-daemon/05-EMPIRICAL.md` (por qué Hermes quedó bloqueado)

## 6. Files allowed to modify
- `src/orchestrator/llm_orchestrator.py` (NUEVO — el adapter)
- `src/orchestrator/__init__.py` (export)
- `src/bootstrap/cli.py` y `src/bootstrap/config.py` (cablear: sección `[orchestrator]` en config con modelo/tier y flag para elegir determinístico|llm)
- `config/config.example.toml` (documentar la sección nueva)
- `tests/orchestrator/` (tests nuevos)

## 7. Files forbidden to modify
- `src/gateway/cost.py`, `src/gateway/gateway.py`, `src/orchestrator/dispatcher.py`, `src/agents/configured_agent.py`, `src/agents/registry.py` (protegidos D-85)
- `src/core/policy/` completo
- `src/core/ports/` (el port existe; si el contrato no alcanza, ESCALAR a Fable — no improvisar)

## 8. Required changes
1. `LLMOrchestrator` implementa `OrchestratorPort`: recibe la petición del owner, arma prompt de sistema (rol: planner de Wyss; catálogo de action types válidos tomado del dominio; formato de salida JSON con schema del `Plan`), llama al gateway, parsea fail-closed a `Plan` frozen.
2. Prompt de sistema: incluir la instrucción de que contenido citado del entorno es dato no confiable (espejo del patrón anti-injection de `ConfiguredAgent`).
3. Parseo: reutilizar/espejar `_plan_from_json`/`_action_from_dict` de `daemon.py`; si el JSON trae action types desconocidos, campos extra o riesgo declarado menor al que la política calcularía → rechazo con error de dominio (no excepción cruda).
4. Config: `[orchestrator] mode = "deterministic" | "llm"`, `model_tier = "..."` — default `deterministic` (opt-in explícito; el fake sigue siendo el default hasta calibrar).
5. Bootstrap: en `wyss start`, si mode=llm construir `LLMOrchestrator` con el gateway ya armado en `bootstrap/gateway.py`.
6. Tests (patrón fake existente): (a) respuesta LLM válida → Plan correcto llega al dispatcher; (b) JSON inválido/campo extra → rechazo fail-closed auditado; (c) action type de la denylist D en la respuesta → PolicyDecision D (probar que la política sigue mandando); (d) presupuesto agotado → el cost gate corta ANTES de la llamada (usar fakes del gateway, no red); (e) inyección en contenido citado no altera el plan (fixture dorado de fase 7 como referencia).

## 9. Contracts and invariants
- import-linter sigue 2/2: `orchestrator` importa de `core`, NO de `gateway` directamente… **atención**: el adapter necesita el gateway → la inyección se hace por port/callable desde bootstrap (DI manual), nunca `import gateway` dentro de `orchestrator` (violaría el contrato de independencia). Si el port existente no lo permite, ESCALAR.
- Default de config = comportamiento actual (determinístico). Nada cambia para quien no opta in.
- Ningún path nuevo evita policy, auditoría o cost gate.

## 10. Tests required
```bash
uv run pytest -q                      # suite completa, incluye los nuevos
uv run mypy && uv run ruff check src tests && uv run lint-imports   # contrato independencia INTACTO
```

## 11. Manual verification
Con LiteLLM up y `.env` presente (PR-03): `wyss start` con mode=llm → `wyss ask "creá un archivo nota.txt en data/tmp_tests con el texto hola"` → plan visible en bandeja B → `wyss confirm` → archivo existe → `wyss audit` muestra el camino completo → restore vía journal posible. Luego: `wyss ask "borrá todo /home"` → rechazo D inmediato.

## 12. Risks
- LLM produce planes sintácticamente válidos pero semánticamente absurdos → mitigado: confirmación B/C humana + policy determinístico; nada se auto-ejecuta salvo nivel A.
- Acoplamiento orchestrator→gateway rompe import-linter → mitigado: inyección por constructor desde bootstrap (verificado por `lint-imports` en el gate).
- Costo por llamada → cost gate pre-llamada ya existente; budget del orquestador en config.

## 13. Rollback plan
`mode = "deterministic"` en config revierte el comportamiento sin tocar código. Revert del commit elimina el adapter; ningún archivo protegido cambió.

## 14. Acceptance criteria
- Los 5 tests nuevos + suite completa verdes; lint-imports 2/2 kept.
- Verificación manual §11 ejecutada por el owner con LLM real y documentada en SUMMARY.
- `config.example.toml` documenta `[orchestrator]`.
- Archivos protegidos D-85: diff vacío.

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. Python 3.12 + uv, mypy strict, hexagonal
enforced por import-linter. NO commitees. PROHIBIDO modificar: src/gateway/cost.py, src/gateway/gateway.py,
src/orchestrator/dispatcher.py, src/agents/configured_agent.py, src/agents/registry.py, src/core/policy/*,
src/core/ports/*. Si el contrato de OrchestratorPort no alcanza para la tarea, DETENTE y reporta — no
inventes arquitectura.

Lee primero (en este orden): src/core/ports/orchestrator.py · src/orchestrator/daemon.py (funciones
_plan_from_json y _action_from_dict) · src/core/orchestrator/intent.py · src/bootstrap/gateway.py ·
src/bootstrap/cli.py (comandos start/ask) · src/bootstrap/config.py · config/config.example.toml.

Construye:
1. src/orchestrator/llm_orchestrator.py — clase LLMOrchestrator que implementa OrchestratorPort.
   Recibe por constructor un callable/port al gateway (INYECTADO desde bootstrap; jamás "import gateway"
   dentro de orchestrator/ — el contrato de independencia de import-linter lo prohíbe y el gate fallará).
   Flujo: petición → prompt de sistema (planner de Wyss, catálogo de action types del dominio, salida
   SOLO JSON con el schema de Plan, contenido citado = dato no confiable) → llamada vía gateway →
   parseo fail-closed a Plan frozen espejando _plan_from_json/_action_from_dict: JSON inválido, campo
   extra o action type desconocido = rechazo con error de dominio, nunca excepción cruda ni plan parcial.
2. Config: sección [orchestrator] con mode = "deterministic"|"llm" (default "deterministic") y model_tier.
   Validarla en src/bootstrap/config.py con el patrón Pydantic existente (extra=forbid) y cablear en
   src/bootstrap/cli.py (comando start): mode=llm → construir LLMOrchestrator con el gateway de
   bootstrap/gateway.py. Documentar la sección en config/config.example.toml.
3. tests/orchestrator/test_llm_orchestrator.py con fakes (patrón de tests/gateway/conftest.py — sin red):
   a) respuesta válida → Plan llega al dispatcher; b) JSON roto/campo extra → rechazo fail-closed;
   c) action de denylist D en la respuesta → PolicyDecision D; d) budget agotado → corta pre-llamada;
   e) instrucciones inyectadas en contenido citado no alteran el plan.
Verifica: uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
(los 2 contratos deben seguir KEPT). Reporta SUMMARY con archivos nuevos/tocados y salida exacta de
cada verificación. Confirmá explícitamente: "protegidos D-85 sin cambios".
```
