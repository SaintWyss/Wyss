# 07 — Operación, despliegue y recuperación

## Topología operativa

Yo opero Wyss principalmente en una PC Linux del owner. El daemon y las bases viven localmente; la web y el APK se conectan por LAN; los providers externos son opcionales.

## Arranque diario

```bash
uv run wyss start
```

En otra terminal:

```bash
uv run wyss web --lan --tls
```

Checklist:

1. verificar versión y cambios recientes;
2. comprobar `config/config.toml`;
3. comprobar permisos de `config/.env` y `data/`;
4. confirmar filesystem con WAL;
5. iniciar daemon;
6. consultar una acción A segura;
7. iniciar web;
8. verificar huella y pairing;
9. revisar pendientes y auditoría.

## systemd de usuario

Yo recomiendo una unidad de usuario para el daemon:

- `WorkingDirectory` al checkout/instalación;
- `ExecStart` con `uv run wyss start` o binario empaquetado;

Para Home Edge yo uso en cambio la unidad de sistema de `deploy/systemd`: necesito UIDs distintos
para que `SO_PEERCRED` sea una frontera real. Yo instalo la unidad sin iniciarla hasta completar el
smoke con:

```bash
scripts/install-system-service.sh saintwyss wyss-edge wyss-home \
  /home/saintwyss/Wyss /ruta/al/checkout-operativo \
  /ruta/al/config.toml /ruta/al/data
sudo systemctl start wyss.service
```

Para rollback yo detengo `wyss.service`, restauro la unidad anterior y vuelvo a cargar systemd. El
instalador copia la configuración como `0600`; no elimina la fuente ni las bases existentes.
- `Restart=on-failure`;
- `UMask=0077`;
- límites de recursos;
- logs en journal;
- sin ejecución como root.

La web LAN puede iniciarse manualmente para mantener la exposición como opt-in.

## Observabilidad

Yo observo:

- daemon vivo y socket disponible;
- provider health;
- pending count y expiraciones;
- fallos de acciones/verificación;
- uso de presupuesto;
- tamaño de DBs;
- rutinas fallidas;
- digest;
- rechazos web 401/403;
- cambios de certificado;
- almacenamiento disponible;
- errores de indexación.

## Datos a respaldar

```text
config/config.toml
config/.env              # cifrado y manejo separado
data/audit.db
data/pending.db
data/client_requests.db
data/routines.db
data/memory.db
data/ledger.db
data/index.db
data/execution/
data/chroma/ o equivalente
data/digests/
data/tls/
data/web_token
data/intake_token
```

Yo no mezclo secretos con un backup común sin cifrado y control de acceso.

## Backup

La opción más segura es detener daemon y web de forma ordenada, y luego:

```bash
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "backups/wyss-${stamp}"
cp -a data "backups/wyss-${stamp}/"
cp config/config.toml "backups/wyss-${stamp}/"
sha256sum "backups/wyss-${stamp}"/data/*.db \
  > "backups/wyss-${stamp}/SHA256SUMS"
chmod -R go-rwx "backups/wyss-${stamp}"
```

Para secretos creo un archivo cifrado separado o uso un gestor de secretos. No confío en permisos POSIX sobre NTFS.

## Restore drill

1. restaurar en un directorio temporal;
2. verificar checksums;
3. apuntar un config de prueba al directorio;
4. iniciar en modo deterministic;
5. consultar auditoría, memoria, rutinas, ledger e índice;
6. probar una lectura A sobre `/tmp`;
7. no ejecutar pendientes viejos automáticamente;
8. verificar tokens/certificados antes de exponer LAN;
9. registrar RPO/RTO.

## Rotación de pairing

```bash
rm data/web_token
```

Después reinicio la web y repito pairing. Esto invalida sesiones existentes.

Para intake:

```bash
rm data/intake_token
```

Yo actualizo n8n después de generar el nuevo bearer.

## Rotación TLS

Antes de aceptar una nueva huella:

1. confirmar que el cambio fue intencional;
2. verificar archivos y host;
3. detener exposición LAN si hay duda;
4. generar/reemplazar certificado;
5. comparar huella por un canal confiable;
6. re-parear APK.

## Provider caído

- el daemon puede informar modo degradado;
- yo cambio temporalmente a deterministic si necesito operación local;
- no configuro fallback silencioso entre modelos de distinto tier;
- reviso presupuesto, URL, credenciales y health;
- no expongo la key en logs.

## Incidente de acción no deseada

1. detener nuevas acciones;
2. preservar audit y journal;
3. ejecutar `wyss undo <task_id> --dry-run`;
4. revisar inversas y estado actual;
5. confirmar undo solo si es seguro;
6. recuperar desde backup si no existe inversa;
7. revisar plan, policy y segunda muralla;
8. agregar prueba de regresión.

## Incidente de secreto indexado/enviado

1. detener daemon/provider;
2. rotar el secreto;
3. preservar traces sin redistribuirlos;
4. eliminar/reconstruir índices afectados;
5. revisar filtros y rutas;
6. verificar backups;
7. documentar alcance.

## Corrupción SQLite o WAL no disponible

Yo detengo el proceso, trabajo sobre copias y no fuerzo `journal_mode` a un modo menos seguro solo para arrancar. Muevo los datos a un filesystem compatible, restauro y verifico integridad.

## Rutinas

Ante una rutina fallida:

- pauso la rutina;
- reviso `last_outcome` y audit;
- verifico el plan guardado;
- pruebo manualmente en un target de prueba;
- reanudo conscientemente;
- no elimino evidencia para ocultar el fallo.

## Upgrade y rollback

1. backup;
2. ejecutar cadena de pruebas;
3. revisar cambios de config/esquema;
4. actualizar en una rama/versión identificada;
5. smoke deterministic;
6. smoke web;
7. smoke provider/dispositivo si aplica;
8. rollback al commit previo si el formato sigue siendo compatible;
9. preferir forward-fix si hubo migración incompatible.

## Evidencia mínima

- timestamp UTC;
- versión/commit;
- config no sensible;
- actor y task ID;
- plan y decisión;
- pending/execution ID;
- eventos de auditoría;
- outputs sanitizados;
- archivos/recursos afectados;
- acción de contención y recuperación.
