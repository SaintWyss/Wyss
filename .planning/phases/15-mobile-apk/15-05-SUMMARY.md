---
phase: 15-mobile-apk
plan: 05
status: complete
completed: 2026-07-11
requirements: [APK-02]
builder: claude
---

# 15-05 — Sección "Parear teléfono" en la SPA

`web/src/surfaces/Parear.tsx` + `api.pair()`/`PairPayload` + grupo **Dispositivos** en la nav (desktop + mobile). Dep `qrcode-generator@2.0.4` (exacta, zero deps, aprobada por el owner en Task 0).

- QR SVG 100% client-side: `pairingQrData` = `JSON.stringify(payload)` exacto (lo que `PairingPayload.parse` nativo espera); `renderPairingQr` = `createSvgTag({cellSize:4, margin:2, scalable})` sobre fondo blanco (contraste para el escáner).
- UI: QR + pasos 01-03 + fp/url en mono para verificación manual (paridad con el panel CLI). Botón regenerar.
- Server sin `--lan --tls` → ErrorNote con el 400 accionable de `/api/pair` (nunca QR roto).
- Vitest 3 tests (round-trip + determinismo); build + oxlint verdes. Bundle rebuildeado a `webui_dist` (el bridge lo sirve de disco sin restart).
