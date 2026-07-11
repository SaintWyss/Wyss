---
phase: 15-mobile-apk
plan: 01
status: complete
completed: 2026-07-11
requirements: [APK-01, APK-03, APK-04]
builder: codex (Kotlin) + Claude (scaffold/build) + owner (checkpoint device)
---
# 15-01 — SPIKE device APROBADO (2026-07-11 19:40)
Evidencia: celu 192.168.100.3 instaló app-debug.apk (25.6M, Capacitor 7.6.7, gradle assembleDebug 2m21s headless); el bridge registró GET / desde la app con 401-sin-token — el request solo llega si el WebView aceptó el cert self-signed, que solo ocurre con match de huella en onReceivedSslError. **A1 (bridge.webView.loadUrl handoff) ✓ y A2 (SslCertificate.saveState→X509→SHA-256→match) ✓ verificados en device real.** 401 esperado (sin cookie — el pairing QR llega en waves 2-4). Gate de waves 2+ ABIERTO.
