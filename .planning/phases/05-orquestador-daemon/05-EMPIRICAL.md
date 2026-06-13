# 05 — Verificación Empírica (Wave 0)

Fecha: 2026-06-13 · Host: Santiago-PC (CachyOS) · Docker 29.5.2 · Plan: 05-01

Cierra los supuestos MEDIUM de RESEARCH (A1-A4) corriendo comandos reales antes de
construir sobre ellos. Contrato **stop-and-revise**: VEREDICTO global PASS solo si los
ítems empíricos pasan; cualquier FAIL escala antes de las waves de implementación.

---

## A1 — API de FastMCP / mcp + round-trip MCP→engine  ·  **PASS**

- **Deps pinneadas (`uv add "mcp>=1.27,<2" "fastmcp>=2.14,<3"`):** resueltas
  `mcp==1.27.2`, `fastmcp==2.14.7` en `uv.lock`. NO se instaló 3.x.
- **Legitimidad (T-05-SC):** `mcp` = SDK oficial del protocolo MCP; `fastmcp` 2.x construido
  sobre `mcp`. Coinciden con el Package Legitimacy Audit de RESEARCH. [OK]
- **Firma real de `FastMCP.run` (refina A1):**
  - `run(self, transport: Transport|None=None, show_banner=True, **transport_kwargs)` —
    `host`/`port` NO son params top-level; pasan por `**transport_kwargs`.
    `mcp.run(transport="http", host="127.0.0.1", port=7420)` funciona.
  - **`run_http_async(self, show_banner=True, transport="http", host=None, port=None,
    log_level=None, path=None, uvicorn_config=None, middleware=None, json_response=None,
    stateless_http=None)`** — variante async con `host`/`port`/`path` EXPLÍCITOS.
  - **Implicación para 05-04/05-05:** el daemon es asyncio; usar
    `await mcp.run_http_async(transport="http", host="127.0.0.1", port=PORT, path="/mcp")`
    en una task, NO `mcp.run()` (que arranca su propio event loop y bloquea).
- **Round-trip MCP tool → `engine.evaluate(plan)`** (cliente in-memory FastMCP `Client(mcp)`):
  tool construye `Plan(Action(type,target))`, llama `engine.evaluate`, devuelve outcome.
  Resultados diferenciados por riesgo: `file.read`→outcome A, `shell.run`/`file.write`→C.
  El gating end-to-end funciona. [PASS]
- **Suite:** `uv run pytest tests/ -q` → **283 passed, 3 skipped** tras el `uv add` (sin regresión).

**VEREDICTO A1: PASS.** El mcp_server de 05-05 se codea contra una API confirmada.

---

## A2 — Imagen Docker oficial de Hermes Agent  ·  **FAIL (resoluble: build local)**

- `docker pull ghcr.io/nousresearch/hermes-agent:latest` → **`unauthorized`**.
  La imagen candidata de RESEARCH **no existe publicada / no es pullable**.
- El `docker-compose.yml` oficial del repo **NO referencia un registry**: usa
  `image: hermes-agent` con **`build: .`** (Dockerfile en la raíz). Servicios `gateway` +
  `dashboard` comparten esa imagen buildeada localmente.
- **Resolución:** clonar `github.com/NousResearch/hermes-agent` y `docker build` local
  (o `docker compose build`). NO hay pull de registry. El compose de 05-05 debe usar
  `build:` apuntando al repo clonado, no `image: ghcr.io/...`.

**VEREDICTO A2: FAIL.** Supuesto de registry roto. Impacto acotado a deployment/compose
de 05-05; no afecta 05-02/03/04 ni la API MCP (A1).

---

## A3 — Deshabilitar built-in tools de Hermes (disabled_toolsets)  ·  **PARCIAL**

- Docs oficiales (`hermes-agent.nousresearch.com/docs/reference/mcp-config-reference`)
  **confirman** el shape de conexión MCP:
  ```yaml
  mcp_servers:
    <server_name>:
      url: "https://.../mcp"
      headers: {}
  ```
- El literal `disabled_toolsets: [memory, web, code, filesystem]` asumido por RESEARCH
  **no aparece** en la doc de referencia MCP. El control de tools built-in es vía el
  comando `hermes tools` / "toolset system" (40+ tools). La key exacta de config YAML
  para apagar TODOS los built-in debe confirmarse contra el schema de la imagen buildeada
  (depende de A2: hay que tener la imagen local primero).

**VEREDICTO A3: PARCIAL.** Formato `mcp_servers` confirmado; la key de disable se cierra
al buildear la imagen (T-05-02 queda pendiente hasta tener la imagen).

---

## A4 — `host.docker.internal` + networking en CachyOS  ·  **PARCIAL-PASS (fix: regla UFW)**

- Con `--add-host=host.docker.internal:host-gateway`, dentro del container:
  `getent hosts host.docker.internal` → **`172.17.0.1`** (gateway del bridge docker0).
  La resolución host-gateway **FUNCIONA** en Docker de CachyOS. [PASS]
- Conectividad TCP container→host (`wget http://host.docker.internal:7420`) → **timeout**.
  - Host escucha OK: `curl http://172.17.0.1:7420` desde el host → `HOST-OK`.
  - Causa: **UFW activo con `policy DROP` en INPUT**; dropea el TCP que llega por docker0.
- **Fix:** abrir el puerto del MCP server solo al subnet del bridge:
  ```
  sudo ufw allow from 172.17.0.0/16 to any port <MCP_PORT> proto tcp
  ```
  (refuerza T-05-01: el server bindea a 127.0.0.1 + regla UFW restringida al bridge,
  nunca 0.0.0.0 abierto). Registrar como op de sistema (no sincroniza).

**VEREDICTO A4: PARCIAL-PASS.** host-gateway resuelve; conectividad requiere 1 regla UFW.
No es blocker de código; es config de deployment per-máquina.

---

## VEREDICTO GLOBAL: **STOP parcial — proceder Waves 1-2, revisar 05-05**

| Item | Veredicto | Bloquea |
|------|-----------|---------|
| A1 FastMCP API + round-trip | **PASS** | nada |
| A2 imagen Hermes | **FAIL** (build local, no pull) | solo deployment de 05-05 |
| A3 disabled_toolsets | **PARCIAL** (cerrar tras build) | solo 05-05 |
| A4 networking CachyOS | **PARCIAL-PASS** (regla UFW) | solo deployment |

**Análisis de impacto:** los fallos (A2/A3/A4) están **confinados al deployment de Hermes
y al wiring del compose** — todos en Plan 05-05. La API contra la que se codea (A1) está
confirmada. Los planes **05-02 (dominio puro), 05-03 (persistencia), 05-04 (daemon +
FakeOrchestrator, Hermes DOWN)** NO dependen de ningún supuesto roto y pueden ejecutarse.

**Revisiones requeridas en 05-05 (antes de ejecutarlo):**
1. Compose: `build:` desde repo Hermes clonado, no `image: ghcr.io/...`.
2. Confirmar la key real de disable de toolsets contra la imagen buildeada (cerrar A3).
3. Daemon: servir MCP con `run_http_async(transport="http", host="127.0.0.1", port, path="/mcp")`.
4. Añadir regla UFW `from 172.17.0.0/16` al runbook de deployment (op de sistema).
