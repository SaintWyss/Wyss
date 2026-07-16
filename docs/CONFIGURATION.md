# Configuración de Wyss

Wyss separa configuración no sensible y secretos:

- `config/config.toml`: estructura, rutas, política, modelos, presupuestos y features;
- `config/.env`: tokens y API keys.

La plantilla canónica es `config/config.example.toml`. Los secretos de ejemplo viven en `config/.env.example`.

## Preparación

```bash
cp config/config.example.toml config/config.toml
cp config/.env.example config/.env
chmod 600 config/.env
```

`load_settings()` carga automáticamente el `.env` ubicado junto al TOML pasado mediante `--config`. Las variables ya exportadas en el proceso tienen precedencia y no son sobrescritas.

## Validación fail-closed

La configuración usa Pydantic con `extra="forbid"`. Un typo, clave desconocida, tipo incorrecto o TOML inválido aborta el arranque con `ConfigError`.

La denylist de nivel D no vive en TOML. Las reglas `[[policy.deny]]` solo pueden **agregar** restricciones a los invariantes built-in.

## Rutas principales

```toml
data_dir = "data"
audit_db = "data/audit.db"
```

Los stores SQLite que exigen WAL deben residir en un filesystem compatible. NTFS/FUSE puede ignorar permisos POSIX y no siempre soporta las garantías esperadas.

## Política

```toml
[policy]
file_count_b = 10
file_count_c = 100
dir_count_c = 5
delete_count_d = 50
sensitive_dirs = ["~/.ssh", "/etc", "/boot", "data", "**/.env*", "**/*.key"]
```

Regla adicional:

```toml
[[policy.deny]]
id = "no-borrar-proyecto-critico"
match_action = "file.delete"
match_target = "~/Data/proyecto-critico/**"
description = "Protección adicional definida por el owner"
```

No existe una opción para desactivar las reglas built-in.

## Gateway de modelos

```toml
[gateway]
global_budget = 50.0
timeout_s = 120.0
trace_retention_days = 90

[gateway.tiers.economico]
provider = "litellm"
model_alias = "qwen-default"
max_tokens = 1024

[gateway.tiers.fuerte]
provider = "anthropic"
model_alias = "claude-opus-4-6"
max_tokens = 4096

[gateway.prices]
qwen-default = 0.0004
claude-opus-4-6 = 0.015

[gateway.agent_budgets]
orchestrator = 2.0
pellegrini = 5.0
```

Providers reconocidos actualmente por bootstrap:

- `litellm`;
- `anthropic`.

Un provider desconocido aborta el boot. Los precios son locales y deben mantenerse actualizados por el owner; el código no debe confiar en que el provider reporte costos correctamente.

## Orquestador

Modo local determinista:

```toml
[orchestrator]
mode = "deterministic"
tier = "economico"
```

Modo LLM:

```toml
[orchestrator]
mode = "llm"
tier = "economico"
budget_usd = 2.0
```

`deterministic` es el default de la plantilla para que el sistema arranque sin red. `llm` requiere un tier válido, secretos disponibles y el provider alcanzable.

La validación manual existente se realizó con Qwen mediante LiteLLM local. Cambiar provider o modelo exige repetir smoke y revisar calidad de planes, costo y límites.

## Daily Assistant

```toml
[digest]
enabled = true
hour = 8
minute = 0
```

La zona horaria operativa está fijada actualmente a Argentina. El digest es solo lectura y se materializa bajo `data/digests/`.

## Intake externo

```toml
[intake]
enabled = true
max_per_minute = 30
```

Con `enabled=false`, el endpoint no debe estar operativo. El bearer se guarda en `data/intake_token` y es distinto de la cookie del pairing móvil.

Toda propuesta externa recibe un piso de riesgo B; nunca se autoejecuta como acción A.

## Agentes

```toml
[[agents]]
agent_id = "pellegrini"
name = "Pellegrini"
domain = "finanzas"
knowledge_bases = []
model_tier = "economico"
budget_usd = 5.0
```

`budget_usd` se deriva al gate cuando no existe un valor explícito en `[gateway.agent_budgets]`. El valor explícito tiene precedencia.

## Ingesta

La sección `[ingest]` admite, entre otros:

- `chunk_size_tokens`;
- `chunk_overlap_tokens`;
- `max_file_bytes`;
- `dir_denylist`;
- `entropy_allowlist`;
- `default_kb_id`;
- `max_attempts`.

No relajar filtros de secretos para resolver falsos positivos sin analizar primero el archivo y el impacto.

## Secretos

Variables conocidas:

```dotenv
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
NOTION_TOKEN=...
LITELLM_MASTER_KEY=...
LITELLM_BASE_URL=http://localhost:4000
```

`LITELLM_BASE_URL` es opcional. Nunca incluir secretos en `config.toml`, logs, traces, issues o screenshots.

Cuando se agregue una nueva variable secreta al `.env.example`, también debe incorporarse a la red de valores protegidos del minimizer en `bootstrap/config.py`.

## Notion

Para operar con Notion:

1. definir `NOTION_TOKEN`;
2. compartir explícitamente páginas y databases con la integración;
3. probar primero una lectura;
4. revisar el preview y el nivel de riesgo antes de confirmar escrituras.

El token configurado no concede acceso a recursos que no hayan sido compartidos con la integración.

## Validación rápida

```bash
uv run python -c "from pathlib import Path; from bootstrap.config import load_settings; print(load_settings(Path('config/config.toml')))"
```

Para probar el modo LLM, iniciar además el gateway correspondiente y ejecutar una instrucción de lectura de bajo riesgo antes de habilitar mutaciones.
