# Wyss — Guía del operador

Referencia diaria del código actual. Para el estado completo y sus límites, ver [`RELEASE_STATUS.md`](RELEASE_STATUS.md).

## 1. Preparación inicial

```bash
uv sync
cp config/config.example.toml config/config.toml
cp config/.env.example config/.env
chmod 600 config/.env
```

La plantilla arranca con orquestador determinista. Para LLM real, editar:

```toml
[orchestrator]
mode = "llm"
tier = "economico"
```

y completar el secreto del provider en `config/.env`.

## 2. Arranque diario

Terminal 1 — daemon:

```bash
uv run wyss start
```

Terminal 2 — interfaz web local o LAN:

```bash
uv run wyss web                 # solo esta máquina, HTTP
uv run wyss web --lan --tls     # teléfono/LAN, HTTPS local
```

- Ejecutar `wyss start` cuando el daemon ya está vivo no debe destruir el proceso existente.
- El daemon administra preguntas, confirmaciones, rutinas, memoria y digest.
- La web depende del daemon para operar; si el bridge está arriba pero el daemon no, la UI debe mostrar un error accionable.

## 3. Flujo principal

```bash
uv run wyss ask "leé tal archivo"
uv run wyss ask "mové tal archivo"
uv run wyss ask "borrá tal archivo"
uv run wyss confirm <pending_id>
uv run wyss undo <task_id> --dry-run
uv run wyss undo <task_id>
uv run wyss audit --limit 50
```

Niveles:

| Nivel | Tipo | Resultado |
|---|---|---|
| A | lectura/diagnóstico | ejecución directa |
| B | modificación normal | confirmación simple |
| C | alto impacto | exige escribir `CONFIRMAR` |
| D | destructivo/prohibido | rechazo absoluto |

La política se reevalúa al confirmar. Si el riesgo subió desde que se creó la propuesta, se exige el nivel nuevo. Si subió a D, no se ejecuta.

## 4. Salidas y lectura segura

Acciones de lectura disponibles:

- `file.read`;
- `file.list`;
- `file.stat`;
- `git status`;
- `git log`;
- `git diff`.

Las salidas están limitadas y deben indicar cuando fueron truncadas. Rutas de secretos, traversals y symlinks maliciosos se bloquean en la segunda muralla.

## 5. Rutinas programadas

Listar:

```bash
uv run wyss routine list
```

Pausar, reanudar o borrar:

```bash
uv run wyss routine pause <routine_id>
uv run wyss routine resume <routine_id>
uv run wyss routine rm <routine_id>
```

Crear desde CLI requiere un plan JSON interno y muestra las próximas ejecuciones antes de guardar:

```bash
uv run wyss routine add \
  "Lectura diaria" \
  cron \
  "0 8 * * *" \
  --plan-json '<plan-json>'
```

La UI web es preferible para creación normal. Reglas operativas:

- cron e intervalos se interpretan en hora Argentina;
- intervalos menores a 60 segundos se rechazan;
- una rutina perdida puede hacer un único catch-up coalescente;
- B/C siempre caen a bandeja;
- D sigue siendo rechazo absoluto;
- cada disparo debe quedar auditado.

## 6. Memoria del owner

Pedir al orquestador que recuerde algo:

```bash
uv run wyss ask "recordá que prefiero reportes breves"
```

La escritura de memoria es una acción B y requiere confirmación.

Administrar hechos:

```bash
uv run wyss memory list
uv run wyss memory edit <fact_id> "nuevo valor"
uv run wyss memory rm <fact_id>
```

Los hechos distinguen tiers `owner` y `external`. Contenido externo debe tratarse como dato no confiable y no como instrucción.

## 7. Daily Assistant

Generar el digest ahora:

```bash
uv run wyss digest
```

Activar generación programada:

```toml
[digest]
enabled = true
hour = 8
minute = 0
```

El digest combina:

- propuestas pendientes;
- snapshot de Pellegrini;
- fallas y últimas corridas de rutinas;
- memoria owner aplicable.

Es solo lectura y se materializa en `data/digests/YYYY-MM-DD.md`.

## 8. Pellegrini

```bash
uv run wyss fin --help
uv run wyss fin ver
```

Los números salen del ledger SQLite y de agregaciones deterministas. El LLM puede redactar una recomendación, pero no calcular saldos ni alterar el ledger sin una acción gateada.

## 9. Notion

No hay un subcomando separado: se usa lenguaje natural mediante `wyss ask` o la web.

Ejemplos:

```bash
uv run wyss ask "leé esta página de Notion: <url>"
uv run wyss ask "consultá esta base de Notion: <url>"
uv run wyss ask "creá una página en Notion con este contenido..."
```

Requisitos:

- `NOTION_TOKEN` en `config/.env`;
- página o database compartida con la integración;
- gateway/orquestador disponible cuando la instrucción se interpreta con LLM.

Lecturas son A. Crear o actualizar es C y debe mostrar preview antes de confirmar.

## 10. Intake n8n

Activar explícitamente:

```toml
[intake]
enabled = true
max_per_minute = 30
```

El bridge genera o usa `data/intake_token`. El endpoint externo es `/api/intake` y requiere su bearer dedicado.

Reglas:

- no acepta la cookie de pairing como credencial;
- token ausente o inválido se rechaza;
- toda propuesta recibe piso B;
- rate limit propio;
- nunca registrar el bearer en logs.

## 11. Teléfono mediante navegador

```bash
uv run wyss web --lan --tls
```

1. Abrir una vez la URL de teléfono impresa por el servidor.
2. Comparar la huella SHA-256 mostrada.
3. Aceptar el certificado local.
4. Agregar a pantalla de inicio cuando se use como PWA.

La cookie dura 30 días. Para rotar pairing web:

```bash
rm data/web_token
```

y reiniciar `wyss web`. Esto desloguea dispositivos existentes.

## 12. APK Android

El cliente nativo está en `mobile/` y usa pairing por QR, WebView y pinning TOFU.

Flujo normal:

1. levantar `wyss start`;
2. levantar `wyss web --lan --tls`;
3. abrir en la web la superficie **Parear**;
4. escanear el QR desde la app;
5. verificar que carga el bridge y mantiene paridad de confirmación B/C.

Ante rotación del certificado, la app debe bloquear el origen hasta volver a parear. No elegir “continuar de todos modos” ante mismatch de fingerprint.

## 13. Auditoría

```bash
uv run wyss audit
uv run wyss audit --limit 200
uv run wyss audit --since 2026-07-16T00:00:00+00:00
```

El CLI lee `audit.db` directamente. Para integraciones locales yo uso el método RPC `audit`, que
consulta el mismo adapter mediante un port, limita cada respuesta a 200 eventos y omite payloads
salvo que yo pida `include_payload: true` explícitamente.

## 14. Undo

```bash
uv run wyss undo <task_id> --dry-run
uv run wyss undo <task_id>
```

- El plan inverso cruza la misma política A–D.
- Un inverso D se rechaza.
- Si el estado cambió, el undo se detiene.
- Solo hay inversas `file.*`; shell y Git no están cubiertos.

## 15. Backups mínimos

Con el daemon detenido, respaldar como mínimo:

```text
data/audit.db
data/pending.db
data/routines.db
data/memory.db
data/ledger.db
data/execution/
data/digests/
config/config.toml
```

Los nombres exactos pueden depender de `data_dir`. No copiar `config/.env` sin cifrado y control de acceso.

Para SQLite WAL, copiar base, `-wal` y `-shm` de forma consistente o usar un método de backup SQLite. No copiar archivos activos a ciegas.

## 16. Parada

Detener por `Ctrl+C` en las terminales correspondientes. Si quedó un proceso huérfano:

```bash
pkill -f 'wyss start'
pkill -f 'wyss web'
```

Usar `pkill` solo después de verificar el proceso con `pgrep -af wyss`.

## 17. Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `config.toml` no existe | plantilla no copiada | copiar `config/config.example.toml` |
| Configuración inválida | typo o clave extra | corregir el campo indicado; el parser es fail-closed |
| Daemon no responde | proceso caído/socket stale | iniciar `uv run wyss start`; revisar terminal |
| “daemon ya corriendo” | proceso sano existente | usarlo o detenerlo de forma controlada |
| LLM degraded | gateway/provider caído | probar LiteLLM/provider, secreto, tier y presupuesto |
| Notion permission error | página no compartida | compartirla con la integración |
| Teléfono 401 | cookie/token rotado | reabrir URL de pairing o volver a parear |
| 403 host/origin | URL distinta de la impresa | usar origen exacto permitido |
| Certificado mismatch en APK | cert o servidor cambió | bloquear, verificar y re-parear |
| Rutina no dispara | daemon apagado, pausa o schedule | `wyss routine list`; revisar estado y hora |
| Digest no aparece | `[digest]` desactivado | activar y reiniciar daemon; probar `wyss digest` |
| SQLite no acepta WAL | filesystem incompatible | mover `data_dir` a disco local compatible |
| Permisos 0600 no aplican | NTFS/FUSE | proteger desde opciones de mount o mover secretos |

## 18. Límites conocidos

- `1.0.0.dev0` identifica desarrollo v1 y no autoriza una publicación final;
- undo limitado a archivos;
- deterministic es el default;
- infraestructura LLM y Notion es externa;
- TLS local requiere confianza TOFU;
- providers externos requieren sus credenciales y autorización propias.

Verificación completa: [`TESTING.md`](TESTING.md). Configuración: [`CONFIGURATION.md`](CONFIGURATION.md).
