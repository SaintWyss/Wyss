---
phase: 15-mobile-apk
plan: 02
status: complete
completed: 2026-07-11
requirements: [APK-02, APK-04]
builder: codex (wave 1, junto al spike 15-01)
---

# 15-02 — Backend GET /api/pair

Endpoint construido en la wave 1 junto al spike (commit 2d52215). `GET /api/pair` en `src/bootstrap/web.py`: cookie-auth normal (sin exención), devuelve `{v:1, url:https://<lan_ip>:<port>, fp:fingerprint_sha256(cert), token}` — los tres strings ya computados sobre la sesión autenticada, cero superficie nueva. Sin `--lan --tls` → 400 `{error:"pairing requiere --lan --tls", accion:"reiniciá con: wyss web --lan --tls"}`. Consumido por la sección Parear de la SPA (15-05) y escaneado por la app (15-04). Verificado E2E en el checkpoint 15-06 (el QR renderizado desde este payload pareó el teléfono).
