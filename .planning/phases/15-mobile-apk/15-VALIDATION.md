# Phase 15 — Mobile APK: Validation Map

Mapa per-task de como se valida cada pieza. Los tests automatizables corren en el entorno; los checkpoints device solo el owner los cierra en el telefono.

## Wave 0 gaps (tests nuevos, creados dentro de sus plans)

| Gap (RESEARCH Wave 0) | Creado en | Comando |
|-----------------------|-----------|---------|
| FingerprintMatcherTest (match SHA-256 puro) | 15-03 Task 1 | `gradlew testDebugUnitTest` |
| PairingPayloadTest (decode/validacion QR) | 15-03 Task 1 | `gradlew testDebugUnitTest` |
| Parear.test.tsx (round-trip payload -> QR) | 15-05 Task 1 | `npm run test -- Parear` |
| test_origin_localhost_collision_still_rejected | 15-02 Task 2 | `pytest tests/bootstrap/test_web.py -k origin_localhost_collision` |
| test_api_pair_requires_tls_and_cookie | 15-02 Task 2 | `pytest tests/bootstrap/test_web.py -k api_pair` |
| Android JUnit framework | ya lo trae `npx cap add android` (15-01) | — |

## Requisito -> Plan -> Tipo de validacion

| Req | Plans | Automatizable | Device-only (checkpoint) |
|-----|-------|---------------|--------------------------|
| APK-01 (instala/abre nativa) | 15-01, 15-06 | assembleDebug produce APK | 15-01 Task 3 (spike), 15-06 Task 2 punto 1 |
| APK-02 (pairing QR: escaneo + generacion) | 15-02, 15-04, 15-05 | pytest api_pair, vitest Parear round-trip, gradlew PairingPayloadTest | 15-06 Task 2 punto 2 (escaneo E2E) |
| APK-03 (TOFU pinning fail-closed) | 15-01, 15-03 | gradlew FingerprintMatcherTest, revision diff (no proceed ciego) | 15-01 Task 3 (A2 device), 15-06 Task 2 punto 4 (cert rotado E2E) |
| APK-04 (same-origin, sin aflojar allowlist) | 15-01, 15-02, 15-03 | pytest test_origin_localhost_collision + suite web, assembleDebug | 15-01 Task 3 (A1 loadUrl renderiza SPA), 15-06 Task 2 punto 2 |
| APK-05 (paridad confirmacion B/C) | 15-06 | suite SPA existente (mismos componentes) | 15-06 Task 2 punto 3 |
| APK-06 (error accionable + re-pairing) | 15-04, 15-06 | grep clearPairing + assembleDebug | 15-06 Task 2 puntos 4-5 |

## Per-task automated verify (resumen)

| Plan-Task | Comando de verificacion |
|-----------|-------------------------|
| 15-01 T1 | `gradlew tasks | grep assembleDebug` |
| 15-01 T2 | `gradlew assembleDebug` -> BUILD SUCCESSFUL + APK presente |
| 15-01 T3 | checkpoint device (A1+A2) — NO automatizable |
| 15-02 T1 | `pytest test_web.py && mypy && ruff && lint-imports` |
| 15-02 T2 | `pytest test_web.py -k "api_pair or origin_localhost_collision"` |
| 15-03 T1 | `gradlew testDebugUnitTest` -> BUILD SUCCESSFUL |
| 15-03 T2 | `gradlew assembleDebug` -> BUILD SUCCESSFUL |
| 15-04 T1 | grep cero fetch/XHR en mobile/www + grep completePairing/scan |
| 15-04 T2 | grep clearPairing + `gradlew assembleDebug` |
| 15-05 T1 | `npm run test -- Parear && npm run lint` |
| 15-05 T2 | `npm run build && grep parear src/App.tsx` |
| 15-06 T1 | suite completa (pytest + vitest + gradlew unit) + APK |
| 15-06 T2 | checkpoint device E2E (APK-01/02/05/06) — NO automatizable |

## Checkpoints device (owner, telefono fisico)

1. **15-01 Task 3** — Spike A1 (loadUrl handoff renderiza SPA) + A2 (SslCertificate.saveState: match procede, mismatch bloquea). GATE de toda la wave 2+. Si falla -> REPLAN.
2. **15-06 Task 2** — E2E final: instala, parea por QR, confirma B/C con paridad, cert rotado bloquea + re-parea, server caido = error accionable.

## Chain de cierre por plan (runbook wyss)

Todo plan con codigo Python pasa la cadena verde antes de commit:
`uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`.
Plans de web/: `npm run test && npm run build && npm run lint`.
Plans de mobile/: `gradlew testDebugUnitTest && gradlew assembleDebug`.
