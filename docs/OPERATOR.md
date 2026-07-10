# Wyss — Guía del operador

Uso diario de Wyss v0.1.0. Referencia rápida: qué correr, desde dónde, y qué hacer cuando algo no anda.

## Arranque

```bash
cd <repo>
uv run wyss start                # daemon (deja la terminal ocupada, o usá nohup)
uv run wyss web --lan --tls      # UI web accesible desde el teléfono, HTTPS
```

- `wyss start` con el daemon ya corriendo NO es un error: el panel te lo dice y seguís usando `wyss ask` directo.
- Sin `[orchestrator]` en `config/config.toml` el daemon corre en modo **deterministic** (demo). Para LLM real: sección `[orchestrator] mode = "llm"` + `config/.env` con credenciales + gateway arriba.
- `wyss web` sin flags = solo esta máquina, HTTP. `--lan` expone a la red local (opt-in), `--tls` sirve HTTPS con cert self-signed auto-generado en `data/tls/` (habilita voz y cookie Secure).

## Teléfono (bridge móvil)

1. `wyss web --lan --tls` imprime dos URLs con token. Abrí la de **Teléfono** UNA vez.
2. Aceptá el certificado (el panel imprime la huella SHA-256 para verificarla).
3. Menú de Chrome → **Agregar a la pantalla de inicio** → queda el ícono Wyss como app.

- El login dura **30 días** y sobrevive reinicios del server (token persistente en `data/web_token`).
- Rotar el token = borrar `data/web_token` y reiniciar `wyss web` (desloguea todos los devices).
- El teléfono **propone y confirma**; el PC decide y ejecuta. Nada se ejecuta sin tu sello.

## Flujo de trabajo

```bash
uv run wyss ask "leé tal archivo"        # nivel A → ejecuta directo, muestra la salida
uv run wyss ask "mové/borrá tal cosa"    # nivel B/C → queda pendiente
uv run wyss confirm <pending_id>         # B: sí/no · C: exige tipear CONFIRMAR
uv run wyss undo <task_id>               # deshace lo aplicado (dry-run + confirmación)
uv run wyss audit                        # historial auditado
uv run wyss search "algo" / wyss index   # conocimiento indexado
uv run wyss fin ver                      # ledger Pellegrini
```

Niveles: **A** lectura/diagnóstico (directo) · **B** modificación normal (confirmación simple) · **C** alto impacto (tipear `CONFIRMAR`) · **D** prohibido (rechazo absoluto, no confirmable).

La política se re-evalúa **al confirmar**: si el riesgo subió desde que se propuso, la palabra exigida es la del nivel más alto. Las lecturas devuelven la salida (capada, honesta si trunca); leer secretos (`~/.ssh`, `.env`…) está bloqueado por la segunda muralla.

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| UI dice "el daemon no está corriendo" | daemon caído | `uv run wyss start` |
| `wyss start` → "ya corriendo" | daemon ya vivo | no es error; `wyss ask` directo, o bajalo con `pkill -f 'wyss start'` |
| Teléfono: 401 "no autorizado" | cookie vencida (30 días) o token rotado | reabrí la URL con token que imprime `wyss web` |
| Teléfono: UI carga pero API muerta | mirá la franja roja `bridge: …` en la UI y la terminal del server: **loguea cada rechazo con su motivo** | según motivo: Host/Origin ajeno = accedé por la URL exacta impresa |
| Aviso de certificado cada vez | cert self-signed | normal UNA vez por device; cero avisos = certs mkcert en `data/tls/` |
| `403 host no permitido` | accediste por un hostname/IP no impreso | usá exactamente la URL del panel (allowlist estricta, sin wildcard) |
| Confirmación rechazada "riesgo re-evaluado subió" | el estado cambió entre proponer y confirmar | pedilo de nuevo; el nuevo pending refleja el riesgo actual |
| Puerto 7777 inaccesible desde el teléfono | firewall | `sudo ufw allow from 192.168.0.0/16 to any port 7777 proto tcp` |

Más detalle del bridge: `docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md` · modelo de seguridad completo: `docs/security/SECURITY_MODEL.md`.

## Límites conocidos (v0.1.0)

- `wyss audit` vía RPC del daemon devuelve lista vacía (stub); el comando CLI lee la DB directo y funciona.
- Sin service worker/offline en la PWA (el cert self-signed lo bloquea; con mkcert instalado en el device se destraba).
- `wyss undo` cubre inversas de `file.*`; shell/git no tienen undo.
- En volúmenes NTFS los `chmod 0600` (token, key TLS) no aplican — el mount los ignora.
