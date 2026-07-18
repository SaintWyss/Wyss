# 05 — Configuración, datos y APIs

## Configuración canónica

Yo separo configuración no sensible en `config/config.toml` y secretos en `config/.env`.

### Raíz

- `data_dir`: directorio de datos de runtime;
- `audit_db`: base de auditoría separada.

Ambos deben vivir en un filesystem local compatible con SQLite WAL.

### Política

```toml
[policy]
file_count_b = 10
file_count_c = 100
dir_count_c = 5
delete_count_d = 50
sensitive_dirs = ["~/.ssh", "/etc", "data", "**/.env*"]
```

Las reglas `[[policy.deny]]` solo agregan restricciones. No pueden remover la denylist built-in.

### Gateway

```toml
[gateway]
global_budget = 50.0
timeout_s = 120.0
trace_retention_days = 90
```

Cada tier define provider, alias y tokens máximos. La tabla de precios local permite calcular costos sin confiar ciegamente en el provider.

### Orquestador

```toml
[orchestrator]
mode = "deterministic" # o "llm"
tier = "economico"
```

Yo uso `deterministic` como default seguro y reproducible.

### Digest

```toml
[digest]
enabled = false
hour = 8
minute = 0
```

### Intake

```toml
[intake]
enabled = false
max_per_minute = 30
```

### Agentes

Las entradas `[[agents]]` definen ID, nombre, dominio, bases de conocimiento, tier y presupuesto. El gate real deriva o usa el presupuesto explícito de gateway.

## Secretos

`config/.env` puede contener:

- `ANTHROPIC_API_KEY`;
- `GOOGLE_API_KEY`;
- `OPENAI_API_KEY`;
- `LITELLM_MASTER_KEY`;
- `LITELLM_BASE_URL`;
- `NOTION_TOKEN`.

Yo cargo el archivo sin sobrescribir variables ya exportadas. Los valores conocidos se incorporan al filtro de secretos del gateway, no a logs o traces.

## Bases de datos

| Archivo | Responsabilidad |
|---|---|
| `audit.db` | eventos auditados |
| `pending.db` | propuestas B/C y TTL |
| `routines.db` | rutinas y últimas ejecuciones |
| `memory.db` | hechos del owner |
| `ledger.db` | transacciones financieras |
| `index.db` | estado de ingesta/frescura |
| `execution/journal.db` | mutaciones e inversas |
| Chroma data | vectores |

Yo separo estas bases para limitar acoplamiento, pero las respaldo como conjunto cuando necesito recuperar un estado completo.

## Datos de conocimiento

El pipeline maneja:

- ruta;
- base de conocimiento;
- tamaño y mtime;
- hash;
- estado de extracción/embedding;
- chunks;
- FTS5;
- vectores;
- exclusiones por secreto;
- fallos y reintentos.

No indexo `.env`, claves privadas ni rutas denegadas.

## Contrato JSON-RPC

El daemon acepta métodos como:

- `ask`;
- `confirm`;
- `home.intent` — intención versionada de un cliente con `message_id` y `request_id`;
- `home.plan.answer` — primera respuesta válida, re-evaluada y serializada por plan;
- `status`;
- `audit` — consulta acotada por `since`, `task_id`, `event_type` y `limit` (1–200);
- `routine.add/list/pause/resume/delete`;
- `memory.list/edit/forget`;
- `digest.today`;
- `intake.propose`.

La CLI usa `data/wyss.sock` `0600`; Home Edge usa exclusivamente `data/wyss-home.sock` `0660`. Yo
configuro `WYSS_HOME_EDGE_USER` con una cuenta de sistema distinta,
`WYSS_HOME_EDGE_GROUP` con el grupo compartido y `WYSS_HOME_SOCKET_PATH` con una ruta absoluta fuera
del data dir privado (por ejemplo `/run/wyss-home/authority.sock`). El servicio prepara su directorio
padre como `0750 owner:grupo`; Wyss verifica permisos, membresía, grupo y peer mediante
`SO_PEERCRED`. Sin esa
configuración no expongo el socket Home. Este canal sólo
admite `home.intent`, `home.plan.answer` y `status`, y no confía en `source` enviado por el caller.
Yo persisto claims Home en `data/client_requests.db` con archivos
DB/WAL/SHM `0600`, cuota y mantenimiento acotado: un replay idéntico recibe la primera respuesta,
una key reutilizada con otro payload falla por conflicto y un efecto ambiguo después de un crash no
se reintenta automáticamente. Yo resuelvo confirmaciones con compare-and-swap de revisión y TTL.
Yo omito el `payload` de auditoría por defecto; sólo el socket owner puede pedirlo explícitamente.

## API web

El bridge expone endpoints para:

- pairing/autenticación;
- chat/ask;
- confirmaciones;
- bandeja;
- estado;
- rutinas;
- memoria;
- digest;
- intake externo;
- QR/pairing de APK.

El código, no una lista manual, es la fuente exacta de rutas. La web aplica token/cookie, host/origin allowlist, TLS y rate limits específicos.

## Action types

Grupos actuales:

- `file.read/list/stat/move/rename/create/write/delete`;
- `git.status/log/diff`;
- `shell.run`;
- `finance.query/record`;
- `notion.read_page/query_database/create_page/update_page`;
- `memory.remember`.

Todo tipo desconocido se trata de forma conservadora.

## Providers

### LiteLLM

Yo lo uso como proxy local opcional para aliases y múltiples modelos.

### Anthropic

Provider directo para tiers configurados.

### Ollama

Se usa para embeddings locales cuando está disponible. Si falla, la búsqueda puede continuar en modo FTS-only.

### Notion

El token solo accede a páginas compartidas explícitamente con la integración. El adapter pagina, limita salida y traduce errores.

## Pairing y tokens

- `data/web_token`: token persistente de web/PWA;
- `data/intake_token`: bearer separado para intake;
- certificado y key en `data/tls/`;
- APK conserva origen/huella mediante almacenamiento nativo.

Borrar un token lo rota y desloguea/requiere re-pairing.

## Retención

- audit: conservación extensa según política;
- traces de modelo: `trace_retention_days`;
- digests: archivos por fecha;
- backups: política explícita y cifrado;
- memoria: editable y borrable por owner;
- pendientes: TTL según riesgo/origen.

## Errores

Yo traduzco errores a mensajes accionables sin incluir secretos. Un adapter devuelve `ToolResult(success=false)` para fallos esperables, en vez de propagar excepciones crudas a todo el proceso.

## Regla de cambio

Cuando agrego una variable, DB, action type, RPC o provider, actualizo config example, parser, validación, filtro de secretos, pruebas, UML y este capítulo.
