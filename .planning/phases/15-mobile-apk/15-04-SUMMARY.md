---
phase: 15-mobile-apk
plan: 04
status: complete
completed: 2026-07-11
requirements: [APK-02, APK-06]
builder: claude
---

# 15-04 — Pantalla de pairing bundled

`mobile/www/` (index.html + pairing.js + pairing.css, paleta wyss). Gate Pitfall 1 verificado: **cero** `fetch(`/`XMLHttpRequest`/`new WebSocket` en el bundle; única comunicación = `Capacitor.Plugins`. `assembleDebug` OK con el bundle sincronizado (`npx cap sync android`).

**Open Question #1 (permiso de cámara ML Kit en WebView bundled): RESUELTA sin fallback.** Se usa `BarcodeScanner.scan()` (one-shot), que delega en el **GMS code scanner** de Play Services: UI de escaneo nativa propia, la app NO pide permiso de cámara. Si falta el módulo GMS, la pantalla lo instala (`installGoogleBarcodeScannerModule`) y pide reintentar. `startScan` (cámara embebida + permiso) no hizo falta.

Estados: scan (default) / error accionable (cert_mismatch: "certificado cambió… si no fuiste vos, no te conectes"; net_error: "verificá wyss web --lan --tls / re-pareá si cambió la IP") con botón Re-parear (`clearPairing`) / ya-pareado (boot path nativo conecta solo). Al cargar consulta `lastError()` (autoritativo) + fragment `#error=` (best-effort). Verificación funcional en device = plan 06.
