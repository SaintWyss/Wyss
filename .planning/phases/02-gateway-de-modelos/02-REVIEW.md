---
phase: 02-gateway-de-modelos
reviewed: 2026-06-12T13:47:08Z
depth: standard
files_reviewed: 34
files_reviewed_list:
  - src/bootstrap/config.py
  - src/bootstrap/gateway.py
  - src/core/domain/__init__.py
  - src/core/domain/config.py
  - src/core/domain/errors.py
  - src/core/domain/gateway.py
  - src/gateway/__init__.py
  - src/gateway/cost.py
  - src/gateway/gateway.py
  - src/gateway/minimizer.py
  - src/gateway/providers/__init__.py
  - src/gateway/providers/anthropic.py
  - src/gateway/providers/fakes.py
  - src/gateway/providers/litellm.py
  - src/gateway/providers/ollama.py
  - src/gateway/router.py
  - src/gateway/secrets_patterns.py
  - src/gateway/traces.py
  - src/gateway/traces_schema.py
  - config/.env.example
  - config/config.example.toml
  - tests/bootstrap/test_gateway_config.py
  - tests/domain/test_gateway_domain.py
  - tests/gateway/conftest.py
  - tests/gateway/test_cost_gate.py
  - tests/gateway/test_e2e_security.py
  - tests/gateway/test_embeddings.py
  - tests/gateway/test_gateway.py
  - tests/gateway/test_minimizer.py
  - tests/gateway/test_providers.py
  - tests/gateway/test_retry.py
  - tests/gateway/test_router.py
  - tests/gateway/test_scaffolding.py
  - tests/gateway/test_traces.py
findings:
  critical: 1
  warning: 10
  info: 9
  total: 20
  fixed: 11
status: fixed
---

# Phase 02: Code Review Report — Gateway de Modelos

**Reviewed:** 2026-06-12T13:47:08Z
**Depth:** standard
**Files Reviewed:** 34
**Status:** issues_found

## Summary

Revisión adversarial de los 19 archivos fuente + 2 archivos de config + 13 archivos de test de la Fase 2 (ModelGateway). La arquitectura general es sólida: el orden de Flow 4 está bien implementado (router → minimizer → gate → provider → record → trace → audit), el retry vive solo en el gateway, el gate de presupuesto re-pasa en cada intento, los providers no reintentan, no hay fallback de tier, y el costo del provider nunca gobierna el gate. Los tests de seguridad e2e son fuertes.

Sin embargo, se encontró **1 issue crítico** que viola directamente el invariante "secrets never egress": la cobertura del minimizer es incompleta para secretos documentados en el propio repo (`GOOGLE_API_KEY`, `OPENAI_API_KEY` formato moderno). Además hay **10 warnings**: dos canales latentes de fuga de secretos (repr de dataclass, capa env-value que silenciosamente no se activa), dos opciones de config que son no-ops silenciosos (`trace_retention_days`, `timeout_s`), errores de red no auditados, y una condición TOCTOU en el gate de presupuesto bajo concurrencia.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Cobertura incompleta de secretos — GOOGLE_API_KEY y OpenAI `sk-proj-` evaden el minimizer y egresan

**Status:** fixed in ae59b10

**File:** `src/gateway/secrets_patterns.py:21-30`, `src/bootstrap/config.py:35`, `config/.env.example:9-13`
**Issue:** El invariante de fase es "un secreto NUNCA egresa". El propio repo documenta cuatro secretos en `config/.env.example`: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `LITELLM_MASTER_KEY`. Pero:

1. `_GATEWAY_ENV_KEYS` (`bootstrap/config.py:35`) solo carga `ANTHROPIC_API_KEY` y `LITELLM_MASTER_KEY` como `env_values`. `GOOGLE_API_KEY` y `OPENAI_API_KEY` quedan FUERA de la red de substring exacto.
2. No existe patrón built-in para Google API keys (formato `AIza...`, presente en gitleaks/secrets-patterns-db que el módulo dice haber usado como referencia). Una Google key real en un prompt **egresa sin bloqueo** — ninguna de las tres fuentes del D-21 la cubre.
3. El patrón `openai_key` (`sk-[A-Za-z0-9]{20,}`) no matchea las keys modernas de OpenAI con formato `sk-proj-...`: tras `sk-`, la secuencia `proj` tiene solo 4 caracteres alfanuméricos antes del guión, así que el regex no alcanza el mínimo de 20 y el resto de la key no contiene otro `sk-`. Una key `sk-proj-` real egresa sin bloqueo. El test `test_minimizer.py:80` usa `"sk-proj0123456789abcdefghij"` (SIN guión después de proj) — un shape que no corresponde al formato real, por lo que el test verde oculta el gap.

**Fix:**
```python
# bootstrap/config.py — cubrir TODOS los secretos documentados en .env.example
_GATEWAY_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "LITELLM_MASTER_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
)

# gateway/secrets_patterns.py — agregar Google y formato moderno de OpenAI
("google_api", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
("openai_proj", re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}")),
```
Y corregir el trap del test a `sk-proj-` con guión para fijar el formato real.

## Warnings

### WR-01: `GatewaySettings.env_values` expone los secretos en el `repr()` por default

**Status:** fixed in 653e2fa

**File:** `src/core/domain/config.py:32`
**Issue:** `GatewaySettings` es un dataclass con repr default. `env_values` contiene los VALORES reales de las API keys cargados al boot. Cualquier `repr(settings)`, `print`, f-string de debugging, mensaje de excepción que incluya el settings, o log estructurado que serialice `WyssSettings` imprime todas las keys en texto plano. Esto es un canal latente que viola "secrets never appear in exceptions/logs" — y es exactamente el tipo de fuga accidental que el diseño dice prevenir.
**Fix:**
```python
env_values: tuple[str, ...] = field(default=(), repr=False)
```

### WR-02: `trace_retention_days` es config muerta — la purga de 90 días no está cableada en ningún lado

**Status:** fixed in 18a3f51

**File:** `src/core/domain/config.py:31`, `src/bootstrap/gateway.py:34-85`
**Issue:** `TraceStore.purge_older_than()` existe y está testeado, pero ningún código de runtime lo invoca: `build_gateway` recibe `settings.trace_retention_days` y lo ignora; el `ModelGateway` nunca purga. El invariante D-22 ("traces vencidos se purgan, retención 90d") no se cumple en producción — los prompts/outputs completos se retienen para siempre. El owner que configura `trace_retention_days = 30` obtiene un no-op silencioso (config que miente).
**Fix:** Invocar la purga en `build_gateway` al boot (o al abrir el `TraceStore`): `traces.purge_older_than(settings.trace_retention_days)`, y documentar que la purga corre por boot hasta que exista el scheduler de Fase 4.

### WR-03: `timeout_s` (D-25) es config muerta — nunca se aplica al cliente httpx

**Status:** fixed in 811fd0e

**File:** `src/bootstrap/gateway.py:34-51`, `src/core/domain/config.py:30`
**Issue:** `GatewaySettings.timeout_s` (default 120s, D-25) llega hasta `build_gateway` y se descarta: el docstring delega en "el caller fija timeout", pero nada en el código conecta `settings.timeout_s` con el `httpx.AsyncClient`. Si el caller no lo fija, el default de httpx es **5 segundos**, no 120 — las llamadas a Claude con `max_tokens=4096` van a timeoutear sistemáticamente. La decisión D-25 queda sin enforcement y el valor del TOML es un no-op silencioso.
**Fix:** O bien `build_gateway` valida/aplica el timeout (`client.timeout = httpx.Timeout(settings.timeout_s)`), o bien deja de recibir un settings con `timeout_s` y el contrato se documenta con un assert explícito. La opción de aplicarlo en el composition root es la que respeta "config gobierna".

### WR-04: Provider de tier no validado — typo en config produce `KeyError` crudo sin auditar

**Status:** fixed in 3674b55

**File:** `src/gateway/gateway.py:174`, `src/bootstrap/config.py:74-81`
**Issue:** `TierConfigModel.provider` es un `str` libre: `provider = "antropic"` (typo) o `provider = "ollama"` pasan la validación Pydantic al boot. El fallo recién aparece en runtime: `self._providers[provider_name]` en `_complete_with_retry` levanta un `KeyError` pelado — sin excepción de dominio, sin `TASK_FAILED` auditado (viola "nada relevante ocurre sin registro"), después de haber pasado router y minimizer. El sistema es fail-fast en todo lo demás, pero acá es fail-late y sin rastro.
**Fix:** Validar en `_to_gateway_settings` que `provider` esté en el set conocido (`{"litellm", "anthropic"}`) levantando `ConfigError` al boot; defensivamente, en `_complete_with_retry` convertir el `KeyError` en error de dominio auditado.

### WR-05: `httpx.ConnectError`/`NetworkError` no se maneja: sin retry y sin auditar

**Status:** fixed in 077be2c

**File:** `src/gateway/gateway.py:184-201`
**Issue:** El loop de retry captura solo `httpx.HTTPStatusError` y `httpx.TimeoutException`. Un `httpx.ConnectError` (LiteLLM caído en localhost:4000 — escenario frecuente: el owner tiene los Docker apagados por default) o `httpx.RemoteProtocolError` propaga crudo desde `ask()`: no se reintenta (aunque es transiente por naturaleza) y **no se emite `TASK_FAILED`** — el fallo no deja rastro de auditoría, violando el requisito transversal de auditoría.
**Fix:** Capturar `httpx.TransportError` (superclase de `ConnectError`, `TimeoutException`, etc.) en la rama transiente, o como mínimo agregar un `except httpx.HTTPError` final que audite `TASK_FAILED` antes de re-raise.

### WR-06: TOCTOU en el gate de presupuesto — llamadas concurrentes pueden exceder el budget

**Status:** fixed in 2de205c

**File:** `src/gateway/cost.py:71-83`, `src/gateway/gateway.py:175-197`
**Issue:** `authorize()` lee el gasto durable y compara, pero no reserva nada. Entre `authorize()` y `record()` hay un `await provider.complete(...)` — punto de suspensión donde otras corutinas corren. N llamadas `ask()` concurrentes con presupuesto restante para 1 sola pasan TODAS el gate (cada una ve el mismo `month_spend()`) y el budget se excede por hasta N-1 llamadas en vuelo. Con el orquestador multi-agente de Fase 5 esto es un escenario real, y "enforced, no advisory" (Pitfall 2) queda debilitado.
**Fix:** Serializar authorize→record con un `asyncio.Lock` por CostTracker más una tabla de reservas en vuelo (sumar estimados pendientes al `month_spend()` en `authorize`, liberarlos en `record`/fallo), o documentar explícitamente el overshoot acotado como riesgo aceptado.

### WR-07: Fallo post-provider (record/trace) deja gasto real sin registrar — el gate subcuenta silenciosamente

**Status:** fixed in c3814ba

**File:** `src/gateway/gateway.py:117-139`
**Issue:** Si `cost.record()` falla (disco lleno, `sqlite3.OperationalError`, o `KeyError` si los prices cambiaron en un reload entre authorize y record), la llamada al provider YA consumió dinero pero el `spend_ledger` no lo registra: todos los `authorize()` futuros subcuentan el gasto real y el presupuesto "enforced" se va corriendo hacia arriba sin que nadie lo sepa. Análogamente, si `traces.write()` falla después de `record`, el caller recibe una excepción y puede reintentar → doble gasto real con una sola respuesta perdida. Ningún fallo en pasos 5-7 se audita.
**Fix:** Envolver pasos 5-7 en try/except que (a) audite `TASK_FAILED` con el motivo y (b) en el caso de fallo de `record`, lo trate como error grave (el estado del gate quedó inconsistente), no como excepción genérica que se pierde aguas arriba.

### WR-08: `CostTracker` no verifica WAL pese a que su docstring afirma "WAL fail-fast vía apply_schema"

**Status:** fixed in 6de7b26

**File:** `src/gateway/cost.py:49-59`
**Issue:** El docstring de `__init__` dice "Abre la DB de gateway (WAL fail-fast vía apply_schema)" — es falso: `apply_schema` no verifica nada, y el loop de PRAGMAs en `CostTracker` ejecuta `PRAGMA journal_mode=WAL` sin chequear el resultado (a diferencia de `TraceStore`, que sí fail-fastea). Un `CostTracker` construido standalone (como hacen todos los tests de `test_cost_gate.py`) sobre NTFS/fuseblk degrada silenciosamente la durabilidad del `spend_ledger` — el estado que gobierna el enforcement del presupuesto. Hoy solo funciona porque en `build_gateway` el `TraceStore` se construye antes sobre el mismo archivo.
**Fix:** Replicar el smoke test WAL de `TraceStore` en `CostTracker` (o extraer un helper compartido `open_gateway_db(path)` que haga connect + chmod + WAL check + apply_schema una sola vez), y corregir el docstring.

### WR-09: El 0600 de traces.db depende del orden de construcción y los fallos de chmod se suprimen sin rastro

**Status:** fixed in eb2473b

**File:** `src/gateway/traces.py:59-63`, `src/gateway/cost.py:55-58`
**Issue:** El invariante T-02-trace-file-perms (traces.db 0600) solo se cumple porque `build_gateway` construye `TraceStore` (que hace chmod) ANTES que `CostTracker` (que no lo hace). Si alguien invierte el orden o construye un `CostTracker` standalone primero, la DB con el spend ledger (y luego los prompts) nace con el umask default (típicamente 0644) y nadie la corrige ni lo detecta: el `contextlib.suppress(OSError)` traga cualquier fallo sin loguear. Además hay una ventana entre `sqlite3.connect()` (archivo creado 0644) y el `chmod`.
**Fix:** Hacer el chmod en el helper compartido de apertura de DB (ver WR-08) para que CUALQUIER camino de creación lo aplique; ante fallo del chmod, emitir al menos un registro (no abortar, pero tampoco silencio total). Idealmente pre-crear el archivo con `os.open(path, os.O_CREAT, 0o600)` antes del connect para eliminar la ventana.

### WR-10: Nadie carga el `.env` — la capa env-value del minimizer se desactiva silenciosamente

**Status:** fixed in 13e29cd

**File:** `src/bootstrap/config.py:133-141`, `config/.env.example:1-17`
**Issue:** `_gateway_env_values()` lee `os.environ`, pero ningún código del repo carga `config/.env` (no hay `python-dotenv` ni parsing propio; verificado por grep). Si el owner crea el `.env` como instruye el archivo de ejemplo pero no exporta las variables manualmente, ocurren dos degradaciones silenciosas: (1) la red de alta precisión del minimizer (substring de valores reales) queda vacía — una capa de seguridad entera apagada sin señal alguna; (2) los providers reciben key `""` y todo falla con 401 recién en runtime. Un valor ausente "se omite — no se loguea" es razonable para el VALOR, pero la ausencia total de las dos claves esperadas merece una señal.
**Fix:** Cargar el `.env` en el bootstrap (parsing trivial stdlib o `python-dotenv` confinado a bootstrap), o como mínimo auditar/advertir al boot cuando `_GATEWAY_ENV_KEYS` esperadas están ausentes del entorno (nombrando la CLAVE, jamás el valor).

## Info

### IN-01: `assert` como control de flujo en el retry — bajo `python -O` se convierte en `raise None`

**File:** `src/gateway/gateway.py:200-201`
**Issue:** `assert last_exc is not None` seguido de `raise last_exc`. Con `-O` los asserts se eliminan y, si el invariante alguna vez se rompiera, `raise None` da `TypeError` opaco.
**Fix:** Reemplazar por `if last_exc is None: raise RuntimeError("retry loop sin excepción registrada")`.

### IN-02: Parsing de respuestas 200 sin guardas — `KeyError` crudo ante shape inesperado

**File:** `src/gateway/providers/anthropic.py:48-53`, `src/gateway/providers/litellm.py:43-50`
**Issue:** `data["usage"]`, `data["content"]`, `data["choices"][0]["message"]["content"]` sin validación: una respuesta 200 con shape distinto (proxy mal configurado, `content: null` en OpenAI-shape) produce `KeyError`/`TypeError` crudo no auditado; un `content` None llega como `text=None` y rompería el `NOT NULL` de traces post-gasto.
**Fix:** Validar las claves esperadas y levantar un error claro (que el gateway pueda auditar) cuando el shape no cumple.

### IN-03: Doble evento COST_RECORDED por llamada exitosa

**File:** `src/gateway/cost.py:115-129`, `src/gateway/gateway.py:143-158`
**Issue:** Cada `ask()` exitoso emite DOS `COST_RECORDED` (uno desde `record()` con `actor_id=agent_id`, otro desde el gateway con `actor_id="gateway"`), ambos con el costo. Quien agregue costos desde el audit log contará doble. El comentario lo declara intencional, pero el riesgo de doble conteo no está señalizado en los eventos.
**Fix:** Distinguir el segundo evento (otro event_type o un flag `correlation: true` en el payload), o eliminar uno.

### IN-04: Fixture `http_client` nunca cierra el AsyncClient — finally muerto

**File:** `tests/gateway/conftest.py:30-38`
**Issue:** El `try/finally` termina en `pass` con un comentario que admite que no cierra nada: cada test que usa la fixture filtra un `AsyncClient` sin cerrar (warnings de recursos, código muerto).
**Fix:** Hacer la fixture async (`pytest-asyncio` ya está en modo auto): `async with httpx.AsyncClient() as client: yield client`.

### IN-05: Test lee el fuente por ruta relativa al CWD

**File:** `tests/gateway/test_gateway.py:198-202`
**Issue:** `Path("src/gateway/gateway.py").read_text(...)` depende de que pytest corra desde la raíz del repo; desde otro CWD da `FileNotFoundError`. Además duplica lo que import-linter ya garantiza.
**Fix:** Resolver desde `__file__` o desde el módulo (`Path(gateway.gateway.__file__)`).

### IN-06: Heurística 4 chars/token subestima la entrada hasta 4x para texto no-inglés/código

**File:** `src/gateway/gateway.py:45,104`
**Issue:** `est_in = len(prompt) // 4` subestima fuertemente tokens para español/código denso/CJK; el gate puede autorizar llamadas cuyo costo real de entrada excede el estimado. Mitigado porque `est_out = max_tokens` domina la estimación, pero conviene dejar registrado el sesgo.
**Fix:** Documentado y aceptable para v1; considerar margen (`len // 3`) si los overruns aparecen en el ledger.

### IN-07: Ventana mensual por comparación lexicográfica de strings ISO

**File:** `src/gateway/cost.py:132-148`
**Issue:** `created_at >= ?` compara TEXT. Funciona mientras todos los timestamps tengan formato idéntico (UTC `+00:00`), pero `record()` acepta `created_at` arbitrario: un string con otro offset u otro formato rompe el orden silenciosamente y distorsiona el gasto del mes.
**Fix:** Documentar que `created_at` debe ser ISO UTC, o normalizar en `record()` (`datetime.fromisoformat(...).astimezone(UTC).isoformat()`).

### IN-08: `_LITELLM_BASE_URL` se captura a nivel de módulo en import-time

**File:** `src/bootstrap/gateway.py:31`
**Issue:** `os.environ.get("LITELLM_BASE_URL", ...)` se evalúa al importar el módulo: setear la variable después del import no tiene efecto, y los tests que la monkeypatcheen post-import no la verán. Inconsistente con el resto de las lecturas de entorno, que ocurren dentro de `build_gateway`.
**Fix:** Mover la lectura adentro de `build_gateway`.

### IN-09: `build_gateway` no expone lifecycle — las conexiones SQLite de CostTracker/TraceStore nunca se cierran

**File:** `src/bootstrap/gateway.py:34-85`, `src/gateway/gateway.py:58-80`
**Issue:** `CostTracker` y `TraceStore` implementan context manager / `close()`, pero `ModelGateway` no los expone ni `build_gateway` devuelve forma de cerrarlos: en el daemon de Fase 4-5 las conexiones quedan abiertas hasta morir el proceso (WAL sin checkpoint final limpio).
**Fix:** Agregar `close()` (o `__aexit__`) a `ModelGateway` que cierre cost y traces, y documentar el ownership en `build_gateway`.

---

_Reviewed: 2026-06-12T13:47:08Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
