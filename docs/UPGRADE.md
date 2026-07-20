# Upgrade y rollback

Aplica a la instalación del owner: checkout operativo + unidades de sistema
(`wyss.service`, `wyss-web.service`, `wyss-panel-bridge.service`) y datos en un
directorio propio (`data/`).

## Antes de actualizar

1. Anotar la versión y el commit vigentes:

   ```bash
   systemctl is-active wyss wyss-web wyss-panel-bridge
   git -C <checkout> rev-parse HEAD
   ```

2. Respaldar estado y secretos (mientras los servicios están detenidos, para que
   SQLite no quede con WAL a medio escribir):

   ```bash
   sudo systemctl stop wyss-web wyss wyss-panel-bridge
   tar czf ~/wyss-backup-$(date +%F).tgz \
       <data-dir> ~/.config/wyss/config.toml <checkout>/config/.env
   ```

   `data/` incluye auditoría, pendientes, rutinas, memoria, ledger, índices y los
   tokens (`web_token`, `intake_token`, `home_edge_token`, tokens OAuth). Perder
   los tokens obliga a re-parear teléfono y panel.

## Actualizar

```bash
cd <checkout>
git fetch origin && git checkout v1.0.0
uv sync --frozen
uv run pytest -q                 # gate local: debe dar 754 passed / 7 skipped
sudo systemctl start wyss wyss-web wyss-panel-bridge
```

Verificación mínima post-arranque:

```bash
uv run wyss status               # daemon vivo, socket disponible
curl -sk https://127.0.0.1:8000/api/status   # bridge responde (401 sin cookie es correcto)
systemctl status wyss-panel-bridge --no-pager | head -5
```

Si la unidad de sistema cambió en la versión nueva, reinstalarla antes de arrancar:

```bash
scripts/install-system-service.sh saintwyss wyss-edge wyss-home \
  <repo> <checkout> <config.toml> <data-dir>
sudo systemctl daemon-reload
```

## Migraciones de datos

Esta versión no requiere migración: los stores SQLite crean sus tablas al abrir y
los esquemas de v0.1.0 son compatibles. Las capacidades nuevas viven en tablas
propias (rutinas, memoria, home). Una actualización parcial (binario nuevo, datos
viejos) arranca sin intervención.

## Rollback

```bash
sudo systemctl stop wyss-web wyss wyss-panel-bridge
cd <checkout> && git checkout <commit-anterior> && uv sync --frozen
tar xzf ~/wyss-backup-<fecha>.tgz -C /        # sólo si los datos quedaron inconsistentes
sudo systemctl start wyss wyss-web wyss-panel-bridge
```

Notas:

- Volver a una versión anterior con datos nuevos es seguro para lectura: las
  tablas desconocidas se ignoran. Las rutinas o memoria creadas en v1.0.0 dejan de
  verse hasta volver a subir.
- El instalador no borra `data/` ni la configuración fuente; el rollback de la
  unidad es reinstalarla desde el commit anterior y `daemon-reload`.
- El APK no hace rollback automático: reinstalar el anterior manteniendo la misma
  firma. El pairing sobrevive salvo que cambie el certificado del bridge; si
  cambia, la app corta por pinning y hay que re-parear con el QR.

## Cliente Android

```bash
cd mobile && npx cap sync android
bash android/gradlew -p android assembleDebug
```

El APK queda en `mobile/android/app/build/outputs/apk/debug/app-debug.apk` y se
instala encima del anterior (misma firma debug). Distribución firmada de release
no está resuelta todavía: ver `docs/RELEASE_STATUS.md`.
