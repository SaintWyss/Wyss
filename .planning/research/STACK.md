# Stack Research

**Domain:** Wyss v1.0 — APK Android (Capacitor), Routine Scheduler, Notion adapter, Daily Assistant, memoria persistente, intake n8n
**Researched:** 2026-07-10
**Confidence:** HIGH (Capacitor, APScheduler, notion-client verified via Context7 + official docs/PyPI) / MEDIUM (patrón de memoria persistente, sin librería única canónica)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `@capacitor/core` + `@capacitor/cli` + `@capacitor/android` | **7.6.7** (línea 7.x, tag `latest-7`) | Envolver la SPA React (`web/`, Vite+Tailwind) en un WebView Android nativo | Capacitor 7 usa `compileSdkVersion`/`targetSdkVersion` **35**, que coincide con el Android SDK 35 recién instalado. Capacitor 8 (última mayor, 8.4.1) ya exige SDK 36 — no instalado, y forzarlo agrega fricción sin necesidad. Requiere Android Studio Ladybug+ y **JDK 21** (ya instalado) — compatibilidad exacta con el entorno actual. |
| `notion-client` (PyPI, alias `notion-sdk-py`, autor ramnes) | **3.1.0** (release 2026-05-12) | Cliente Python oficial-equivalente de la API de Notion (SDK JS traducido 1:1) | Cliente de facto para Python — soporta Python 3.8–3.14 (cubre 3.12 del core), tiene `AsyncClient` nativo (compatible con el daemon asyncio de Wyss), y retry/backoff automático en 429 y 5xx configurable vía `RetryOptions`. Va en capa adapter (`adapters/notion/`), nunca en `core/`. |
| APScheduler | **3.11.3** (línea 3.x estable) | Motor de Routine Scheduler (rutinas programadas → bandeja de confirmación) | **NO usar APScheduler 4.0** — sigue en alpha (`4.0.0a1`) sin release estable ni ruta de migración garantizada; no apto para producción. La 3.x trae `AsyncIOScheduler`, que se integra directo al event loop del daemon existente sin bloquear, y tiene job stores persistentes (`SQLAlchemyJobStore` sobre SQLite) para sobrevivir reinicios del daemon. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@capacitor-mlkit/barcode-scanning` (capawesome-team) | **latest 7.x** (compatible Capacitor 7) | Escaneo de QR para el pairing app↔daemon | Plugin más mantenido para barcode/QR en Capacitor 2026 (el viejo `capacitor-community/barcode-scanner` está deprecado). Usa Google ML Kit nativo en Android — más pesado (~unos MB) que un decoder JS puro, pero sin fricción de permisos WebView. Requiere agregar permisos de cámara + flash en `AndroidManifest.xml`. |
| `jsQR` o `zxing-js` (alternativa liviana) | latest | Decodificar QR desde un `<video>` ya abierto vía `getUserMedia` en la SPA, sin plugin nativo | Si el pairing es un flujo único (no escaneo recurrente) y ya se resolvió el permiso de cámara en el WebView (ver gotcha abajo) para voz/audio en v0.1.0, puede alcanzar con JS puro y evitar sumar ML Kit nativo al APK. Evaluar tamaño de APK vs esfuerzo de permisos antes de decidir. |
| `SQLAlchemyJobStore` (parte de `apscheduler[sqlalchemy]`) o `MemoryJobStore` | (viene con apscheduler 3.11.3) | Persistencia de rutinas programadas entre reinicios del daemon | Usar `SQLAlchemyJobStore` sobre un SQLite propio (no el de FTS5/audit) si las rutinas deben sobrevivir un restart del daemon — que es el caso, dado que el daemon es persistente pero puede reiniciarse. `MemoryJobStore` solo si se acepta perder rutinas en cada restart (no recomendado para Wyss). |
| `httpx` (ya en el venv, usado por notion-client internamente) | (la que ya trae el proyecto vía otras deps) | Transporte HTTP para `notion_client.AsyncClient` | Ya es dependencia transitiva probable del proyecto (LiteLLM/gateway usa httpx-like clients); no agrega un segundo cliente HTTP nuevo si ya está presente — verificar en `uv.lock` antes de sumarlo dos veces. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Android Studio Ladybug (2024.2.1) o más nuevo | Build nativo Android / Gradle wrapper que genera `cap add android` | Ya instalado según contexto (SDK 35 + JDK 21). Confirmar que Gradle del proyecto generado usa AGP compatible con Capacitor 7 (no forzar AGP 8.13 que es el que pide Capacitor 8/SDK 36). |
| `npx cap sync android` | Sincroniza `web/dist` + plugins nativos al proyecto Android generado | Correr después de cada build de la SPA y después de instalar/actualizar cualquier plugin Capacitor. |

## Installation

```bash
# Capacitor core (en web/, junto a la SPA existente)
npm install @capacitor/core@latest-7 @capacitor/android@latest-7
npm install -D @capacitor/cli@latest-7

# QR / barcode scanning
npm install @capacitor-mlkit/barcode-scanning

# Inicializar proyecto nativo Android (una sola vez)
npx cap add android
npx cap sync android
```

```bash
# Backend Python — SOLO en capa adapter, nunca en core/
uv add notion-client==3.1.0        # adapters/notion/
uv add "apscheduler==3.11.3"       # adapters/scheduler/ (o infra/)
uv add sqlalchemy                  # si se usa SQLAlchemyJobStore (probable ya presente)
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Capacitor 7.6.7 (SDK 35) | Capacitor 8.x (SDK 36) | Solo si se actualiza el Android SDK a 36 y no hay urgencia de shippear ya — Capacitor 8 es la línea activa a futuro, pero migrar SDK + AGP ahora es trabajo extra no pedido por el milestone. |
| APScheduler 3.11.3 + `AsyncIOScheduler` | asyncio puro (`asyncio.sleep` + loop propio) | Si las rutinas son pocas, simples (intervalos fijos) y no necesitan expresiones cron ni persistencia real — pero se pierde cron-like scheduling, misfire handling y persistencia lista para usar. Para "tareas programadas que caen a bandeja" con expectativa de horarios tipo cron, APScheduler 3.x ahorra reescribir ese motor a mano. |
| APScheduler 3.11.3 | Cron del sistema (crontab) + comando CLI que golpea el daemon | Si se quisiera desacoplar el scheduler del proceso daemon (ej. ejecutar aunque el daemon esté caído) — pero rompe el patrón "todo pasa por el daemon + CognitivePolicyEngine" y complica auditoría; no recomendado dado el constraint de que ninguna acción evite la política cognitiva. |
| `notion-client` (ramnes/notion-sdk-py) | `ultimate-notion` (built on notion-sdk-py) | Si se quisiera una API más "pythonic"/ORM-like sobre páginas y bases de datos Notion en vez de llamadas 1:1 al API REST — agrega una capa de abstracción extra que no es necesaria si el adapter de Wyss ya modela sus propios ports/DTOs. |
| `@capacitor-mlkit/barcode-scanning` (nativo) | `jsQR`/`zxing-js` sobre `getUserMedia` (JS puro) | Si el pairing QR es un flujo único y se prefiere no sumar ML Kit nativo al tamaño del APK — pero requiere resolver el permiso de cámara del WebView a mano (ver gotcha). |
| DIY memoria (markdown MEMORY.md por agente + FTS5/ChromaDB ya existentes) | `mem0ai` u otro framework de memoria vectorial+grafo | Solo si en el futuro Wyss necesitara memoria multi-usuario con extracción automática de hechos y modelo de scopes (user_id/agent_id/run_id) — para un único owner con infra de indexado ya construida (SQLite FTS5 + ChromaDB embebido), sumar un framework externo es sobre-ingeniería y violaría el constraint de stdlib-only en core/. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| APScheduler 4.0 (`4.0.0a1` o cualquier `4.0.0aN`) | Alpha pre-release, sin garantía de compatibilidad hacia atrás ni ruta de migración estable a julio 2026; no recomendado para producción según el propio proyecto | APScheduler 3.11.3 (última estable de la línea 3.x) con `AsyncIOScheduler` |
| `capacitor-community/barcode-scanner` (plugin viejo) | Deprecado, basado en ZXing viejo, requiere el truco de hacer el WebView transparente para mostrar la cámara detrás — hack fragile y ya reemplazado por el ecosistema | `@capacitor-mlkit/barcode-scanning` (ML Kit, mantenido por capawesome-team) |
| Capacitor 8.x junto con Android SDK 35 | Capacitor 8 requiere `compileSdk`/`targetSdk` 36 — con SDK 35 instalado, el build de Gradle falla o fuerza una descarga/actualización de SDK no planeada para este milestone | Capacitor 7.6.7, que calza exacto con SDK 35 |
| `mem0ai` / frameworks de memoria vectorial de terceros para memoria del owner | Wyss ya tiene SQLite FTS5 + ChromaDB embebido operativos (KNOW-01 a KNOW-06 validados) — sumar otro motor de memoria duplica infraestructura, agrega dependencia pesada en una capa que debe mantenerse stdlib-only en el núcleo, y estos frameworks están pensados para multi-usuario, no para un owner único con MEMORY.md por agente ya especificado (AGENT-04) | Persistir memoria como archivos MEMORY.md por agente (patrón ya usado en el propio Claude Code del owner) + indexarlos con el ChromaDB/FTS5 ya existente para recall semántico cuando haga falta |
| Bypass de `onReceivedSslError` con `handler.proceed()` a secas en código nativo | Es el método "rápido" para ignorar errores de certificado, pero Android/Chromium lo documentan como solo-para-desarrollo: acepta CUALQUIER certificado, no solo el self-signed esperado — abre a MITM en cualquier red | `network_security_config.xml` con `trust-anchors` apuntando al certificado self-signed específico de Wyss embebido en `res/raw/`, referenciado desde `AndroidManifest.xml` vía `android:networkSecurityConfig` — confía SOLO en ese certificado, no en cualquiera |

## Stack Patterns by Variant

**Si el certificado self-signed del bridge es fijo (no rota por sesión/pairing):**
- Empaquetar el certificado (o su hash/pin) dentro del proyecto Android nativo generado (`android/app/src/main/res/raw/` + `network_security_config.xml` con `trust-anchors`).
- Porque el proyecto nativo generado por `cap add android` persiste entre `cap sync` — es seguro versionarlo y no se sobrescribe.

**Si el certificado se regenera por pairing/sesión (cada QR genera un cert nuevo):**
- Se necesita un mecanismo dinámico: o bien el WebView acepta el cert vía un plugin nativo custom que valida contra el hash recibido en el QR (TOFU — trust on first use), o se distribuye una CA raíz fija de Wyss y cada cert de sesión se firma con esa CA (entonces `network_security_config.xml` confía en la CA raíz, no en cada leaf cert).
- Porque `network_security_config.xml` estático no puede aceptar certs que cambian en cada instalación/sesión sin reconstruir el APK.
- **Verificar con el owner/código existente del bridge cuál de los dos esquemas usa antes de implementar** — no se pudo confirmar en este research (ver Gaps).

**Si el escaneo QR es solo para el flujo de pairing (una vez, no recurrente):**
- Preferir JS puro (`jsQR`) sobre `getUserMedia` ya que reduce tamaño de APK vs sumar ML Kit nativo completo.
- Resolver el permiso de cámara del WebView (override `onPermissionRequest`/`WebChromeClient` en `MainActivity`) — gotcha de "doble capa" de permisos en Android WebView (el popup de permiso del OS no implica que el WebView conceda el recurso; hay que otorgar explícitamente `RESOURCE_VIDEO_CAPTURE`). Si v0.1.0 ya resolvió esto para audio/voz, replicar el mismo patrón para video.

**Si las rutinas programadas necesitan sintaxis tipo cron (ej. "todos los lunes a las 9am"):**
- Usar `CronTrigger` de APScheduler 3.x en vez de `IntervalTrigger`.
- Porque cubre expresiones cron completas sin reimplementar parsing de horarios a mano.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `@capacitor/core@7.6.7` | Android SDK 35, JDK 21, Android Studio Ladybug (2024.2.1)+ | Confirmado en docs oficiales de Capacitor 7.0 y en el issue #7920 del repo (CapacitorWebView no compila con SDK < 35 en 7.1.0+) |
| `@capacitor-mlkit/barcode-scanning` | Capacitor 7.x, iOS deployment target ≥ 15.5 (no relevante para este milestone, solo Android) | Requiere CocoaPods en iOS (no aplica), en Android solo permisos de manifest |
| `notion-client==3.1.0` | Python 3.8–3.14 | Cubre Python 3.12 del core sin conflicto |
| `apscheduler==3.11.3` | Python 3.9+, funciona con asyncio nativo vía `AsyncIOScheduler` | No requiere AnyIO (eso es v4); se integra directo al loop existente del daemon |

## Notas de constraint (hexagonal / NTFS)

- **Core stdlib-only:** `notion-client`, `apscheduler` y cualquier dep de Capacitor van en capas adapter (`adapters/notion/`, `adapters/scheduler/` o `infra/`), nunca importadas desde `core/`. El `CognitivePolicyEngine` y los ports existentes deben seguir sin conocer estas libs — se exponen detrás de interfaces propias (ej. `SchedulerPort`, `NotionPort`).
- **NTFS (`/mnt/hdd/Data/...`):** proyecto Android generado por `cap add android` crea muchos archivos con permisos ejecutables (`gradlew`, scripts) — en NTFS los bits de permiso Unix no se preservan de forma nativa (dependen de las opciones de montaje `uid`/`gid`/`umask` del automount). Si `./gradlew` falla con "Permission denied" tras clonar/sync, es un síntoma de este gotcha conocido de NTFS, no un bug de Capacitor — mitigar corriendo `sh gradlew` explícito o ajustando el montaje, no reinstalando nada.
- **notion-client / apscheduler no tienen ninguna fricción NTFS particular** (paquetes Python puros/wheels estándar, se instalan igual que el resto del venv ya operativo en `.venv/`).

## Sources

- Context7 `/websites/capacitorjs` — server.url / cleartext / androidScheme (config schema)
- Context7 `/agronholm/apscheduler` — AsyncScheduler v4 (foreground/background), migración v3→v4, estado de v4.0
- [Capacitor Security guide](https://capacitorjs.com/docs/guides/security) — self-signed cert / WebView
- [Android Network Security Configuration](https://developer.android.com/privacy-and-security/security-config) — oficial, `trust-anchors`
- [Handling Self-Signed Certificates in Android WebView](https://sslinsights.com/how-to-handle-self-signed-certificates-in-android-webview/) — MEDIUM confidence, patrón verificado contra doc oficial de Android
- [Updating to 7.0 | Capacitor Documentation](https://capacitorjs.com/docs/updating/7-0) — SDK 35 / JDK 21 / Android Studio Ladybug
- [GitHub issue #7920 ionic-team/capacitor](https://github.com/ionic-team/capacitor/issues/7920) — CapacitorWebView requiere SDK ≥ 35
- [@capacitor-mlkit/barcode-scanning npm](https://www.npmjs.com/package/@capacitor-mlkit/barcode-scanning) — plugin QR mantenido 2026
- [APScheduler PyPI](https://pypi.org/project/APScheduler/) y [4.0.0a1](https://pypi.org/project/APScheduler/4.0.0a1/) — confirma 3.11.3 estable, 4.0 alpha
- [notion-client PyPI](https://pypi.org/project/notion-client/) — v3.1.0, mayo 2026, Python 3.8–3.14
- [notion-sdk-py GitHub (ramnes)](https://github.com/ramnes/notion-sdk-py) y [Client reference](https://ramnes.github.io/notion-sdk-py/reference/client/) — AsyncClient, RetryOptions, httpx
- [Agent Memory & Knowledge Systems Compared (2026 Guide)](https://fountaincity.tech/resources/blog/agent-memory-knowledge-systems-compared/) — MEDIUM confidence, comparación mem0 vs markdown/vector DIY
- [AI Agent Memory 2026 (mem0.ai blog)](https://mem0.ai/blog/state-of-ai-agent-memory-2026) — MEDIUM confidence, scope model de mem0 (multi-usuario) vs necesidad single-owner de Wyss
- WebSearch (sin Context7 disponible para notion-client/apscheduler versión exacta) — verificado cruzando PyPI + GitHub releases, HIGH confidence en números de versión

---
*Stack research for: Wyss v1.0 — APK móvil, scheduler, Notion adapter, memoria*
*Researched: 2026-07-10*
