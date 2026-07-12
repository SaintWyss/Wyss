---
phase: 15-mobile-apk
plan: 06
status: complete
completed: 2026-07-11
requirements: [APK-01, APK-02, APK-05]
builder: owner (checkpoint E2E device)
---

# 15-06 — Checkpoint E2E device APROBADO

Owner instaló el APK final (actualizó encima, misma firma debug) en el teléfono, abrió la app → pantalla de pairing bundled → **escaneó el QR de la sección "Parear" de la web** → la app quedó pareada y entró sola a Wyss cargado desde el bridge (loadUrl nativo tras el pinning TOFU).

**Confirmado en device real:**
- APK-01: app nativa instalable que abre Wyss ✓
- APK-02: pairing por QR sin tipear (escaneo ML Kit → completePairing → handoff) ✓
- APK-03/04: la app entró = el cert self-signed pasó el pinning por match de huella y el loadUrl al origen del bridge funcionó (ya validado en spike 15-01, re-confirmado E2E) ✓

Cita del owner: "anduvo, entré desde el teléfono donde veo el qr". Fase 15 completa; milestone v1.0 cerrable.
