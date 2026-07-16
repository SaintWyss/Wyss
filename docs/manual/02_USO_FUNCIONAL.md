# 02 — Uso funcional

## Flujo principal

```text
instrucción → intención → plan → política → confirmación → ejecución → verificación → auditoría
```

Yo considero este flujo una invariante. Ningún productor de planes debe crear un camino alternativo que evite política o auditoría.

## Daemon

```bash
uv run wyss start
```

El daemon conserva:

- socket local;
- pendientes;
- scheduler;
- memoria;
- ledger;
- digest;
- acceso a herramientas;
- orquestador determinista o LLM.

Si ya está corriendo, el comando informa el estado en vez de iniciar una segunda instancia.

## Preguntar

```bash
uv run wyss ask "leé el archivo X"
uv run wyss ask "mové el archivo X a Y"
```

Resultados esperables:

- ejecutado;
- pendiente;
- rechazado;
- necesita aclaración;
- degradado por provider no disponible;
- falló con detalle accionable.

## Confirmar

```bash
uv run wyss confirm <pending_id>
```

Yo vuelvo a evaluar la política antes de aceptar la palabra. Si el riesgo sube de B a C, la confirmación simple deja de ser válida. Si sube a D, rechazo.

## Undo

```bash
uv run wyss undo <task_id> --dry-run
uv run wyss undo <task_id>
```

El undo:

- calcula inversas;
- verifica el estado actual;
- muestra preview;
- pasa por la misma política;
- aplica en orden inverso;
- se detiene ante el primer fallo.

Actualmente cubre acciones `file.*` compatibles; no promete deshacer shell o Git.

## Auditoría

```bash
uv run wyss audit --limit 100
```

La CLI consulta la base directa. El método RPC `audit` sigue siendo un stub, por lo que no lo confundo con la lectura funcional de la CLI.

## Indexación y búsqueda

```bash
uv run wyss index ~/Data --bc personal --dry-run
uv run wyss index ~/Data --bc personal
uv run wyss search "contrato" --kb personal
uv run wyss status
```

Yo excluyo secretos y rutas denegadas. Si Ollama no está disponible, la búsqueda puede degradarse a FTS5.

## Finanzas

```bash
uv run wyss fin add-ingreso 1000 sueldo
uv run wyss fin add-gasto 250 comida
uv run wyss fin ver
```

Las sumas se calculan en SQL/dominio, no por LLM.

## Rutinas

```bash
uv run wyss routine add "revisión" cron "0 8 * * *" --plan-json '{...}'
uv run wyss routine list
uv run wyss routine pause <id>
uv run wyss routine resume <id>
uv run wyss routine rm <id>
```

Cada disparo reconstruye un plan y pasa por política. Las acciones B/C quedan pendientes. El catch-up coalesce disparos perdidos para evitar múltiples ejecuciones.

## Memoria

```bash
uv run wyss ask "recordá que prefiero informes breves"
uv run wyss memory list
uv run wyss memory edit <fact_id> "nuevo valor"
uv run wyss memory rm <fact_id>
```

Yo distingo memoria declarada por el owner de contenido externo. La memoria se inyecta como dato, no como instrucción ejecutable.

## Digest

```bash
uv run wyss digest
```

Puede incluir:

- pendientes;
- finanzas;
- fallas y últimas rutinas;
- memoria owner limitada.

El digest es solo lectura.

## Notion

Con `NOTION_TOKEN` configurado y páginas compartidas con la integración, el planner puede producir:

- `notion.read_page` nivel A;
- `notion.query_database` nivel A;
- `notion.create_page` nivel C;
- `notion.update_page` nivel C.

Yo pruebo primero en una página descartable.

## Intake n8n

Al activar:

```toml
[intake]
enabled = true
max_per_minute = 30
```

Wyss crea un bearer separado en `data/intake_token`. Una propuesta externa tiene piso de riesgo B y nunca usa la cookie del teléfono.

## Web y PWA

```bash
uv run wyss web
uv run wyss web --lan --tls
```

La versión LAN:

- detecta IP;
- genera o reutiliza TLS;
- usa allowlist exacta de host/origin;
- crea token persistente;
- muestra pairing;
- permite proponer y confirmar.

## Android

El APK usa:

- pantalla de pairing incluida;
- escaneo QR con ML Kit;
- pinning TOFU de la huella;
- carga del origen HTTPS del bridge;
- re-pairing ante rotación o fallo.

## Errores frecuentes

| Síntoma | Acción |
|---|---|
| daemon no disponible | iniciar `wyss start` |
| config inválida | revisar campo exacto informado |
| WAL no soportado | mover `data_dir` a filesystem local |
| provider caído | usar deterministic o reparar gateway |
| pending expirado | generar una nueva propuesta |
| riesgo escaló | revisar y confirmar al nuevo nivel |
| 401 web | repetir pairing o rotar token conscientemente |
| certificado cambió | verificar causa y re-parear, no aceptar ciegamente |
| Notion 404/restricted | compartir recurso con la integración |

## Regla operativa

Yo no concedo una allowlist amplia para “hacer que funcione”. Cada herramienta recibe el mínimo alcance necesario y los errores se resuelven sin perforar la segunda muralla.