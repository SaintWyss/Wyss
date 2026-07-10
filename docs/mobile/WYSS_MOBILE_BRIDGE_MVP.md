# Wyss Mobile Bridge MVP

**Fecha:** 2026-07-09 · **Estado:** verificado E2E vía curl-como-teléfono (LAN real).

## Qué hace

Controla el Wyss del PC desde el teléfono en la **misma red local**. El PC es la
autoridad y el ejecutor; el teléfono solo propone y confirma. No hay lógica de
ejecución en el cliente: la SPA existente (ahora responsive) habla con el mismo
bridge HTTP, que a su vez habla con el daemon por Unix socket. Todo el camino
ask → plan → política A-D → confirmación → ejecución → auditoría es el mismo
que en el escritorio — el móvil no agrega ningún path nuevo de ejecución.

```
teléfono (browser) ── http://<ip-pc>:7777 ──> wyss web --lan ── unix socket ──> daemon
                        (token + cookie)        (bridge FastAPI)                 (policy/executor)
```

## Qué NO hace todavía

- No hay app nativa ni PWA instalable (es la web responsive en el browser).
- No expone nada a internet: LAN only, sin túneles.
- Dictado por voz: el botón aparece solo si el browser lo soporta, y sobre
  `http://<ip-lan>` los browsers lo bloquean (exigen HTTPS/localhost). En el
  teléfono, por ahora, usá el teclado (el dictado del teclado de Android/iOS
  funciona igual: es texto). El fallback de texto es siempre el path principal.
- El pairing vive en memoria del proceso: reiniciar `wyss web` invalida la
  sesión del teléfono (hay que re-abrir la URL con el token nuevo).

## Cómo levantarlo

```bash
# 1. Daemon (autoridad y ejecutor)
uv run wyss start --config config/config.toml

# 2. UI web en modo LAN (opt-in explícito)
uv run wyss web --lan --port 7777 --config config/config.toml
```

El panel imprime dos URLs:

```
PC:       http://127.0.0.1:7777/?token=<token>
Teléfono: http://192.168.x.x:7777/?token=<token>
```

Sin `--lan`, `wyss web` bindea SOLO 127.0.0.1 (default seguro, igual que siempre).

### Firewall

Si UFW está activo con policy DROP, abrí el puerto solo para la LAN:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 7777 proto tcp
```

## Pairing del teléfono

1. En el teléfono, abrí la URL "Teléfono" (tipeala o pasala por el canal que quieras).
2. Wyss valida el token una vez y lo deja en cookie HttpOnly SameSite=Strict.
3. Listo: la UI queda autenticada hasta que el proceso `wyss web` se reinicie.

No existe envío de comandos sin autenticar: cualquier request sin cookie/token
válido → 401 en TODO path (incluidos los estáticos).

## Uso desde el teléfono

- **Chat**: escribí (o dictá, si está disponible) la tarea. El dictado solo llena
  el input editable — nunca envía solo; revisás el texto y tocás Enviar.
- Wyss responde con el plan propuesto y su **nivel de riesgo** (chip A/B/C/D).
- **Nivel B**: botón Aprobar. **Nivel C**: gate que exige tipear `CONFIRMAR`.
- **Bandeja** (tab inferior, con badge): propuestas pendientes con countdown TTL,
  Aprobar/Rechazar. Las propuestas expiran solas (auto-reject por TTL).
- Tras confirmar, la card muestra el resultado real: `Ejecutado — plan … completado`
  o `Falló — <causa>`.
- **Auditoría**: últimos eventos (comando recibido, plan creado, decisión de
  política, confirmación, ejecución).

## Modelo de seguridad

- **Bind opt-in**: sin `--lan` nada escucha fuera de 127.0.0.1.
- **Host allowlist exacta**: con `--lan` solo se aceptan `127.0.0.1`, `localhost`
  y el IP LAN detectado de la máquina. Cualquier otro `Host` → 403 (mitiga DNS
  rebinding). Ídem `Origin`.
- **Token de pairing**: 32 bytes urlsafe generados por corrida, comparados con
  `compare_digest`, viajan una vez por URL y quedan en cookie HttpOnly.
- **El teléfono jamás decide riesgo**: el bridge reenvía al daemon; el nivel A-D
  lo asigna el `CognitivePolicyEngine` determinístico del PC y la denylist D es
  inamovible. La segunda muralla del executor re-evalúa antes de cualquier I/O.
- **HTTP plano en LAN**: el token/cookie viajan sin TLS dentro de tu red. Es el
  trade-off del MVP — no usarlo en redes que no controlás. HTTPS local (mkcert)
  es el upgrade natural si hace falta.

## ⚠ LAN only

`--lan` expone la UI a **toda tu red local**. La allowlist + token gatean, pero
no lo dejes corriendo en redes ajenas/públicas. Nunca port-forwardees este
puerto al exterior.

## Smoke test (verificado 2026-07-09)

Con daemon `mode="llm"` + `wyss web --lan --port 7778` sobre sandbox
`~/.wyss-smoke/` (transcripción real, curl simulando el teléfono):

1. `POST /api/ask` sin cookie → **401** (no hay ejecución sin pairing).
2. `GET /?token=…` con Host LAN → **302** + cookie HttpOnly.
3. `GET /api/status` con `Host: evil.com` + cookie válida → **403**.
4. Ask: *"Creá … /home/…/.wyss-smoke/mobile/mobile_hello.txt … hello from phone"*
   → `{"outcome":"pending", "risk":"C"}` — **el archivo NO existe todavía**.
5. `GET /api/pending` → card con `risk_level: C`, `outcome: CONFIRM_STRONG`, TTL.
6. `POST /api/confirm/<id> {"approve":true}` →
   `{"accepted":true,"success":true,"detail":"plan … completado (1 pasos)"}`.
7. `cat mobile_hello.txt` → `hello from phone` ✓.
8. Audit: `command.received → plan.created → confirmation.requested →
   confirmation.answered → task.completed` ✓.
9. Peligroso: *"Eliminá /etc/passwd"* → `{"outcome":"rejected",
   "reasons":["denylist: system-files-write"]}` + evento `policy.decision`
   ("plan rechazado por política") en audit ✓.

Queda por verificar manualmente en un teléfono físico: render de la bottom-nav,
el gate CONFIRMAR táctil y el pairing tipeando la URL (el contrato HTTP ya está
probado end-to-end).

## Troubleshooting (del smoke físico 2026-07-09)

**Síntoma: la UI carga en el teléfono pero "la API no funciona".** Diagnóstico en orden:

1. **¿El daemon corre?** El bridge y el daemon son DOS procesos: `wyss start` +
   `wyss web --lan --tls`. Sin daemon, la UI carga y `ask`/`confirm` devuelven
   503 ("el daemon no está corriendo" — el strip superior lo dice).
2. **Mirá el strip superior de la SPA:** ahora distingue `bridge: <motivo>` (rojo,
   la API es inalcanzable y dice por qué: 403 origen, sesión vencida, red) de
   "el daemon no está corriendo" (bridge OK, falta `wyss start`).
3. **Mirá la terminal del server:** el middleware loguea cada rechazo con el
   motivo real (`403 host no permitido: Host=...`, `403 origen no permitido:
   Origin=... Sec-Fetch-Site=...`, `401 sin token válido`). Antes era mudo.
4. **Probá `https://<ip>:<puerto>/api/status` directo en el browser del teléfono**
   (con la sesión pareada): 200 con JSON = bridge sano, el problema es otro.
5. **Origin `null`:** Chrome Android con el cert self-signed aceptado puede mandar
   `Origin: null` en los POST same-origin. El bridge lo acepta SOLO cuando
   `Sec-Fetch-Site: same-origin` lo respalda (header que el JS no puede forjar);
   cross-site sigue en 403. Si tu browser no manda Sec-Fetch-* (muy viejo),
   actualizalo o usá Chrome/Firefox.
6. **Cookie:** si el server se reinició, el token cambió: volvé a abrir la URL
   con token nueva (la SPA muestra "Sesión vencida").

## Limitaciones conocidas

- Voz sobre `http://<ip>`: bloqueada por contexto inseguro. **Resuelto en PR-10**:
  `wyss web --lan --tls` sirve HTTPS (cert self-signed auto-generado; huella
  SHA-256 impresa para verificar en el teléfono; mkcert opcional en `data/tls/`)
  y el dictado se destraba.
- Token visible en la URL de pairing (historial del browser del teléfono);
  se invalida reiniciando `wyss web`. Con `--tls` además viaja cifrado.
- Un solo token por corrida: todos los devices comparten sesión.
- La UI no hace push: la Bandeja se refresca por polling (5s el strip; botón
  "actualizar" en la lista).

## Próximo PR sugerido

PWA manifest para "instalar" Wyss en el home screen (diferido de PR-10).
