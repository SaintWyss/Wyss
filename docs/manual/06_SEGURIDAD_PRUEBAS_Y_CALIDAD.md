# 06 — Seguridad, pruebas y calidad

## Modelo de seguridad

Yo no trato al LLM, al contenido indexado ni a una automatización externa como fuentes confiables. La autoridad se divide:

- owner: intención y confirmación;
- política: riesgo definitivo;
- adapters: validación del efecto concreto;
- auditoría: evidencia;
- LLM: propuesta no confiable.

## Amenazas principales

| Amenaza | Ejemplo | Control |
|---|---|---|
| prompt injection | archivo pide ejecutar comandos | contenido como dato, minimización y política |
| plan peligroso | LLM propone `rm -rf` | denylist D y shell fail-closed |
| cambio entre propuesta y confirmación | symlink o reglas cambian | re-evaluación fresca |
| traversal/symlink | ruta escapa del objetivo | resolución y segunda muralla |
| carrera de confirmación | doble click/dispositivo | resolve atómico en PendingStore |
| pending vencido | confirmación tardía | TTL duro y reaper |
| robo de pairing | URL/token filtrado | TLS, cookie, rotación y allowlist |
| MITM móvil | certificado reemplazado | pinning TOFU |
| intake externo abusivo | n8n comprometido | bearer propio, rate limit y piso B |
| secreto al modelo | `.env` en contexto | patrones built-in + valores exactos |
| costo descontrolado | loop de provider | presupuesto pre-llamada |
| corrupción SQLite | filesystem sin WAL | fail-fast y backups |

## Niveles A–D

Yo asigno base levels por action type y luego escalo por:

- cantidad de archivos/directorios;
- sensibilidad de rutas;
- deletes masivos;
- reglas deny built-in y de owner;
- estimación del plan, que solo puede subir riesgo;
- contexto fresco al confirmar.

Nivel D siempre rechaza.

## Segunda muralla

Los adapters verifican:

- paths resueltos;
- symlinks;
- secretos;
- flags Git de escritura;
- pipes y comandos shell peligrosos;
- allowlists;
- backups e inversas;
- resultado post-ejecución.

Yo no confío en que la clasificación previa haya cubierto cada detalle del sistema operativo.

## Auditoría

Los eventos relevantes incluyen:

- comando recibido;
- plan creado;
- decisión de política;
- propuesta pendiente;
- confirmación;
- acción completada/fallida;
- rutina disparada;
- digest generado;
- undo;
- incidentes de provider.

Los payloads evitan secretos y datos crudos innecesarios.

## Pruebas Python

```bash
uv run pytest
uv run mypy
uv run ruff check src tests
uv run lint-imports
```

La suite cubre:

- dominio y policy;
- prompts peligrosos;
- dispatcher;
- daemon y confirmación;
- pending TTL/carreras;
- filesystem/shell/Git;
- undo;
- gateway/costos/minimizer;
- ingesta/retrieval;
- web;
- scheduler;
- memoria;
- digest;
- intake;
- Notion con red simulada;
- CLI.

## Pruebas web

```bash
cd web
npm install
npm run test
npm run build
npm run lint
```

La ruta exacta debe coincidir con el workspace actual. Yo verifico pairing, chat, bandeja, errores, rutinas, memoria, digest y QR.

## Pruebas Android

```bash
cd mobile/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

Además ejecuto checkpoints en teléfono real:

- instalación;
- escaneo QR;
- pinning correcto;
- bloqueo ante huella cambiada;
- confirmación B/C;
- error accionable cuando el server cae;
- re-pairing.

## Pruebas opt-in

- NTFS: `WYSS_TEST_NTFS=1`;
- providers reales;
- Notion real;
- LLM judge;
- hardware/teléfono.

Yo no las ejecuto en CI genérico si requieren secretos o dispositivos, pero registro evidencia.

## CI

El workflow raíz actual valida la cadena Python. Para una release completa yo exijo además jobs web y Android.

## Calidad arquitectónica

- core stdlib-only;
- capas laterales independientes;
- bootstrap como composition root;
- todo productor usa el mismo dispatch;
- ningún LLM asigna riesgo final;
- ninguna acción D es confirmable;
- adapters sin `shell=True`;
- errores esperables como resultados tipados;
- secretos fuera de trazas.

## Supply chain

Yo debería mantener:

- lockfiles;
- dependency updates revisadas;
- auditoría de dependencias;
- SBOM para releases;
- firma/checksum de APK y binarios;
- secret scanning;
- protección de ramas;
- acciones fijadas por versión/digest según política.

## Definición de terminado

Una feature de Wyss necesita:

1. modelo/port;
2. implementación;
3. policy/base level;
4. segunda muralla;
5. auditoría;
6. pruebas;
7. UI/CLI cuando corresponde;
8. documentación;
9. smoke real si toca provider o dispositivo;
10. rollback o desactivación.

## Regla de seguridad

Yo nunca soluciono un test o integración relajando silenciosamente una denylist, allowlist, host/origin o verificación TLS.