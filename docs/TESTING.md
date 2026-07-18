# Testing y gates de Wyss

Wyss tiene tres superficies de validación distintas:

1. backend/CLI/daemon Python;
2. SPA web;
3. cliente Android Capacitor.

Una release no debe declararse validada usando solo una de ellas.

## Cadena Python canónica

```bash
uv sync
uv run pytest -q
uv run mypy
uv run ruff check src tests
uv run lint-imports
```

Esta cadena está automatizada en `.github/workflows/ci.yml` para pull requests y pushes a `main`.
El gate incluye además `uv run ruff format --check src tests` y usa el lock sin resolver versiones
nuevas mediante `uv sync --locked`.

### Qué protege

- dominio, política A–D y denylist;
- daemon, JSON-RPC, pending store y TTL;
- execution adapters, verificaciones y undo de archivos;
- gateway, minimización, presupuestos y providers mockeados;
- indexación y retrieval;
- agentes, ledger, rutinas, Notion, memoria, digest e intake;
- bridge web del lado Python;
- contratos hexagonales.

### Marcadores opt-in

`pyproject.toml` declara marcadores para pruebas que no corren como una suite normal en cualquier host:

- `ntfs`: requiere `WYSS_TEST_NTFS=1` y un mount NTFS/FUSE real;
- `integration`: consume servicios reales según variables de entorno;
- `gateway`: providers, router y gateway;
- `llm_judge`: consume presupuesto de un modelo.

No habilitar pruebas con secretos o servicios reales en CI sin aislamiento y límites explícitos.

## Web

```bash
cd web
npm ci
npm run test
npm run lint
npm run build
```

La suite web cubre componentes y flujos de la SPA. El build valida TypeScript y genera el bundle consumido por el bridge y el cliente móvil.

El workflow raíz ejecuta esta cadena en un job bloqueante e independiente. Un cambio de SPA no se
puede integrar si fallan tests, lint o build.

## Android

Desde el proyecto Android generado bajo `mobile/android`:

```bash
cd mobile
npm ci
npx cap sync android
ANDROID_HOME="$HOME/Android/Sdk" bash android/gradlew -p android testDebugUnitTest assembleDebug
```

El workflow raíz repite la preparación de Capacitor y el build Android en un job bloqueante con
Node 24 y Java 21. En hosts locales sin `ANDROID_HOME` o Android SDK disponible, la cadena falla
de forma explícita en lugar de omitir el APK.

Validaciones automatizadas relevantes:

- decodificación del payload de pairing;
- comparación de fingerprint SHA-256;
- build del APK;
- integración del WebView y plugins a nivel de compilación.

Un build exitoso no sustituye pruebas físicas de cámara, QR, certificados, almacenamiento y WebView.

## Smoke del daemon

```bash
uv run wyss start
```

En otra terminal:

```bash
uv run wyss ask "leé /tmp/wyss-smoke.txt"
uv run wyss audit --limit 20
uv run wyss digest
uv run wyss routine list
uv run wyss memory list
```

Verificar:

- el socket del daemon se crea y responde;
- una lectura A ejecuta y devuelve salida;
- B/C quedan pendientes;
- C exige `CONFIRMAR`;
- D se rechaza sin posibilidad de bypass;
- la auditoría CLI contiene comando, plan, decisión y resultado.

## Smoke LLM

El modo deterministic no prueba providers.

Para validar LLM:

1. configurar `[orchestrator] mode = "llm"`;
2. iniciar LiteLLM o el provider declarado;
3. confirmar secretos y presupuesto mínimo;
4. ejecutar una lectura A sintética;
5. revisar el plan propuesto y las trazas sin secretos;
6. probar una mutación B/C sobre archivos temporales;
7. confirmar que el modelo nunca decide el nivel de riesgo.

Repetir esta validación para cada combinación provider/modelo relevante. La aceptación previa con Qwen vía LiteLLM no garantiza otros modelos.

## Smoke Notion

Con una página de prueba compartida con la integración:

- leer página;
- consultar database con más de una página de resultados;
- verificar 429/retry mediante test o entorno controlado;
- crear o actualizar únicamente después del preview y confirmación;
- comprobar que tokens y contenido crudo sensible no aparecen en audit/traces.

## Smoke intake

Con `[intake] enabled = true`:

- request sin bearer: rechazada;
- bearer incorrecto: rechazado y auditado sin registrar el token;
- bearer correcto: propuesta creada;
- plan originalmente A: elevado al menos a B;
- rate limit: aplicado;
- cookie de pairing: no aceptada como credencial del intake.

## Smoke web y teléfono

```bash
uv run wyss web --lan --tls
```

Probar desde un dispositivo real:

- pairing inicial;
- cookie persistente;
- lectura A con salida visible;
- propuesta B;
- confirmación C escribiendo `CONFIRMAR`;
- rechazo de host/origin ajeno;
- mensaje accionable si el daemon está caído;
- rotación de `data/web_token`.

## Smoke APK

El cierre de Phase 15 ya registró instalación y pairing QR en teléfono real. Para una release nueva repetir:

1. instalar o actualizar APK;
2. escanear el QR desde la pantalla Parear;
3. verificar pinning TOFU;
4. ejecutar lectura A;
5. confirmar B/C con paridad respecto de la web;
6. rotar certificado y confirmar bloqueo fail-closed;
7. borrar pairing y volver a parear;
8. probar server caído y error accionable.

## Filesystems

Probar por separado cuando el despliegue usa varios volúmenes:

- ext4/btrfs local;
- NTFS/FUSE;
- symlinks hacia otros mounts;
- Trash real por volumen;
- SQLite WAL en cada ubicación configurada.

No extrapolar permisos POSIX ni comportamiento de Trash entre filesystems.

## Gate mínimo de pull request

Todo PR debe ejecutar, según su alcance:

| Cambio | Gate obligatorio |
|---|---|
| Python/core/daemon | pytest + mypy + Ruff + import-linter |
| Web/SPA | test + lint + build, bloqueantes en CI |
| Android | sync Capacitor + unit tests + assembleDebug, bloqueantes en CI |
| Configuración | tests de bootstrap + boot con plantilla |
| Seguridad/política | dangerous prompts + re-evaluación + segunda muralla |
| Operación móvil | smoke físico cuando afecte pairing, TLS, QR o WebView |

## Gate de release formal

- commit exacto identificado;
- todas las cadenas verdes;
- APK/artefactos generados desde ese commit;
- checksums y firma;
- smoke de daemon, LLM, Notion, intake, web y APK;
- upgrade y rollback probados;
- límites conocidos actualizados en `RELEASE_STATUS.md`.
