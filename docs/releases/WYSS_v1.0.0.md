# Wyss v1.0.0

Release de la línea v1: Wyss como autoridad única sobre PC, web LAN, teléfono y
panel del hogar. Alcance funcional = fases 9–16 del milestone «Producto final».
Cambios detallados en [`CHANGELOG.md`](../../CHANGELOG.md).

## Alcance

| Superficie | Estado |
|---|---|
| Daemon + CLI (`wyss`) | Release |
| Bridge web LAN + PWA | Release |
| Cliente Android (APK) | Release con firma **debug** — sin canal de distribución |
| Home Edge (reminders, timers, agenda, Spotify) | Release, opt-in por configuración |
| Panel ESP32 (`wyss-home-panel`) | Repositorio propio, versionado aparte |

## Evidencia de validación

Cadena completa ejecutada desde el commit de esta release, en la máquina del owner
(CachyOS, Python 3.13, Node 22, JDK 21 + SDK 35):

| Gate | Resultado |
|---|---|
| `uv run pytest -q` | 754 passed, 7 skipped |
| `uv run mypy src tests` | sin issues, 216 archivos |
| `uv run ruff check src tests` | sin hallazgos |
| `uv run lint-imports` | 2 contratos kept, 0 broken |
| `npm run test` (web) | verde |
| `npm run lint` (web) | verde |
| `npm run build` (web) | bundle 329 kB (106 kB gzip) |
| `npx cap sync android` | verde |
| `gradlew testDebugUnitTest` | verde |
| `gradlew assembleDebug` | APK 25.6 MB |

Smokes funcionales previos aprobados por el owner: bridge en teléfono real (v0.1.0),
pairing QR + pinning TOFU en dispositivo físico (fase 15), digest, intake, Notion,
memoria y rutinas con reloj real (fases 9–13), y el panel contra la autoridad Unix
(fase 16).

## Artefactos

```bash
uv build                       # dist/wyss-1.0.0.tar.gz y .whl
cd dist && sha256sum * > SHA256SUMS
cd mobile && npx cap sync android && bash android/gradlew -p android assembleDebug
```

Los checksums se publican como asset de la release, no dentro del repositorio: un
archivo de hashes commiteado cambiaría el árbol del que se derivan.

Reproducibilidad: el sdist y el wheel se construyen con `hatchling` desde el tag; el
lockfile (`uv.lock`) fija las dependencias. El APK **no** es reproducible bit a bit
(firma debug local y timestamps de Gradle).

## Limitaciones declaradas

- Firma release del APK y actualización over-the-air: no resueltas. La instalación
  es manual, encima de la versión previa y con la misma firma debug.
- `undo` cubre sólo operaciones `file.*`.
- Los permisos `0600` no se aplican sobre NTFS/FUSE.
- El certificado del bridge es self-signed: la confianza es TOFU y un cambio de
  certificado obliga a re-parear el teléfono.
- El modo `deterministic` sigue siendo el default de la plantilla; el modo LLM está
  validado con Qwen vía LiteLLM local y cada provider nuevo requiere su prueba.

## Actualización

Ver [`docs/UPGRADE.md`](../UPGRADE.md), incluido el rollback y el respaldo de `data/`
(tokens de pairing incluidos).
