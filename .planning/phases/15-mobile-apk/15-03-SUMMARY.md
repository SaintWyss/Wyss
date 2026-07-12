---
phase: 15-mobile-apk
plan: 03
status: complete
completed: 2026-07-11
requirements: [APK-03, APK-04]
builder: codex (Kotlin) + Claude (verify/commit)
---

# 15-03 — Pinning real + PairingPlugin

Kotlin (desvío autorizado: el proyecto ya era Kotlin, plan decía Java). 16 tests JVM verdes (`testDebugUnitTest`), `assembleDebug` OK.

**Contrato para JS (usado por plan 04):** plugin `Pairing` con `completePairing({payload: string})` (reject accionable si `PairingPayload.parse` falla), `pairingState() → {paired}`, `clearPairing()`, `lastError() → {error}` (lee y LIMPIA `last_error`; fuente de verdad — el fragment `#error=code` es best-effort vía `bridge.appUrl`).

- `FingerprintMatcher.matches(der, pinnedFp)`: full digest, case-insensitive, null/blank/prefijo → false.
- `PairingPayload.parse`: null ante v!=1, no-https, host no-RFC1918, campos blank, JSON roto.
- `PinnedWebViewClient`: `proceed()` SOLO en match; mismatch/excepción → `cancel()` + `onTrustFailure("cert_mismatch")`; `onReceivedError` main-frame → `net_error`. Sin gate BuildConfig.DEBUG.
- `MainActivity`: boot path — pairing persistido → instala client + `loadUrl(url/?token=)` en `webView.post` (sin postDelayed). Spike eliminado.
- Dep de test agregada: `org.json:json:20240303` (testImplementation, solo JVM).
