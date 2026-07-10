# Wyss — Modelo de Seguridad

**Última revisión:** 2026-07-09 (PR-08 Security Re-Audit). Consolida las reglas
que estaban repartidas en `docs/13`, el target architecture y el código.

## Principio

Wyss tiene acceso amplio al sistema del owner, pero **jamás ejecuta sin criterio**.
El acceso amplio se compensa con capas que TODAS deben pasar antes de tocar el disco.
El LLM **solo propone**; el nivel de riesgo lo asigna un motor determinístico; la
denylist de nivel D vive en código y no es removible por configuración.

## Capas de defensa (en orden)

1. **Denylist D determinística** (`core/policy/builtin_deny.py`, `Final`). La config
   TOML solo AGREGA reglas, nunca vacía estas. Si pudiera, el nivel D dejaría de ser
   absoluto editando un archivo.
2. **Nivel por acción** (`base_levels`) — un tipo de acción desconocido cae a **C**
   fail-closed, nunca A.
3. **Agregados anti-bypass** (`engine._aggregate_level`) — conteos de archivos/dirs,
   borrados, y toque de directorios sensibles escalan el nivel del plan entero.
4. **`estimated_risk` solo SUBE** (POL-04) — el LLM puede subir el riesgo, jamás bajarlo.
5. **Confirmación con TTL** — B pide `s`, C pide `CONFIRMAR` literal; la propuesta
   vence (auto-reject) y **una propuesta vencida no se ejecuta aunque el reaper no
   haya corrido** (chequeo de `expires_at` en `daemon._confirm`, PR-08).
6. **Re-evaluación al confirmar** — al confirmar, el plan se re-evalúa con el engine
   ANTES de validar la palabra; si ahora es D/REJECT, se rechaza aunque la palabra sea
   correcta. Si el riesgo re-evaluado SUBIÓ (p.ej. B→C), la palabra exigida es la del
   nivel nuevo — `s` no alcanza para un plan que hoy es C
   (`test_confirm_escalated_risk_requires_stronger_word`). El pending store **no es la
   autoridad**; la política sí (`test_confirm_reevaluates_and_rejects_now_dangerous`).
   Doble confirm no re-ejecuta: `resolve()` es atómico
   (`UPDATE … WHERE status='pending'` + rowcount; tests `test_double_confirm_executes_only_once`,
   `test_double_resolve_is_atomic`).
7. **Segunda muralla en el adapter** (`filesystem._second_wall`) — resuelve el path
   real y re-evalúa. Bloquea si el riesgo resuelto supera `max_risk` o si el
   **componente-archivo final es un symlink que redirige** (fix F3, PR-08: los
   symlinks de directorio de infraestructura tipo `~/Data → /mnt/hdd/Data` ya no son
   falsos positivos).
8. **Journal antes de mutar** → **verify** → **audit** append-only.

## Niveles de riesgo

| Nivel | Significado | Ejemplos |
|---|---|---|
| **A** | Directo, sin confirmación | `file.read`, `file.list`, `file.stat`, `git.status/log/diff`, `knowledge.query`, `finance.query` |
| **B** | Confirmación simple (`s`) | `file.move`, `file.rename`, `finance.record` |
| **C** | Confirmación fuerte (`CONFIRMAR`) | `file.write/create/delete`, `shell.run` (allowlisted), `git.commit/push`, tipo desconocido (fail-closed) |
| **D** | Rechazo absoluto | ver denylist abajo |

## Denylist D (código, inamovible)

| Regla | Qué bloquea |
|---|---|
| `mass-delete` | Borrado recursivo fuera de papelera, o > umbral agregado de borrados |
| `wyss-self-modify` | Write/delete sobre config/data del propio Wyss |
| `audit-tamper` | Write/delete sobre `audit.db` |
| `secret-exfiltration` | Acceso a `.env`, `*.key`, `id_rsa*`, `~/.ssh/**` (incluye **lecturas**) |
| `system-files-write` | Write/delete bajo `/etc`, `/boot`, `/usr`, **`/sys`, `/proc`, `/var/lib`, `/root`** (ampliado PR-08) |
| `git-force-push-main` | `git push --force` a main/master |
| `disk-format` | `shell.run` con mkfs/fdisk/parted/`dd if=` |
| **`shell-fetch-pipe-exec`** | `shell.run` que canaliza descarga a intérprete (`curl\|bash`, `wget\|sh`, `\|python`, `\|perl`) — nuevo PR-08 |
| **`shell-privilege-escalation`** | `shell.run` con `sudo`/`su`/`doas`/`pkexec` — nuevo PR-08 |
| **`shell-rm-bypass`** | `shell.run` con `rm`/`rmdir`/`shred` como binario (el borrado va por `file.delete`: papelera+journal) — nuevo PR-08 |
| **`shell-recursive-delete`** | `rm -rf`/`-fr`/`-r` embebido en args de shell — nuevo PR-08 |
| **`shell-perm-destructive`** | `chmod 777`/`000`, `chmod -R`, `chown -R` — nuevo PR-08 |
| **`shell-firewall-tamper`** | Deshabilitar/vaciar firewall: `ufw disable`, `systemctl stop/disable/mask firewalld|nftables`, `iptables -F`, `nft flush` (los reads como `status` NO matchean) — nuevo PR-08 |

La denylist ahora inspecciona también **argumentos de shell** (`DenyRule.arg_substrings`),
no solo el binario, para tipificar el pipe-a-intérprete sin bloquear usos benignos
(`grep`, `curl` a archivo). Todas las condiciones de una regla se cumplen a la vez (AND).

## Comportamiento ante prompts peligrosos (verificado por tests)

`tests/security/test_dangerous_prompts.py` blinda esta tabla de forma determinística:

| Prompt | Resultado |
|---|---|
| Delete /etc/passwd | **D** `system-files-write` |
| Write bajo /sys, /proc, /root | **D** `system-files-write` |
| Delete home folder (recursivo) | **D** `mass-delete` |
| Read/upload SSH keys o .env | **D** `secret-exfiltration` |
| `curl … \| bash` | **D** `shell-fetch-pipe-exec` |
| `sudo rm -rf /` | **D** `shell-privilege-escalation` |
| Deshabilitar firewall (`ufw disable`, `systemctl stop firewalld`, `iptables -F`) | **D** `shell-firewall-tamper` |
| `rm` por shell (directo o `rm -rf` embebido) | **D** `shell-rm-bypass` / `shell-recursive-delete` |
| `chmod -R 777` / `chown -R` | **D** `shell-perm-destructive` |
| `mkfs` / format disco | **D** `disk-format` |
| `git push --force main` | **D** `git-force-push-main` |
| Modificar repo del owner | **C** confirmable (no es sistema) |
| Instalar paquete (tipo desconocido) | **C** fail-closed |
| Mover 120 archivos de ~/Data | **≥ C** por agregación |
| Leer un archivo | **A** directo |
| `grep -r TODO src` (pipe benigno) | **no D** |

Aunque el LLM alucine un plan destructivo con `estimated_risk: A`, la denylist gana
(test `test_llm_cannot_downgrade_dangerous_plan`).

## Lecturas (PR-11)

Las lecturas son nivel A pero NO están fuera del perímetro:

- `file.read/list/stat` pasan la **segunda muralla**: leer `.env`/`~/.ssh` resuelve
  **D** (`secret-exfiltration`, que cubre lecturas) y se bloquea + audita.
- La salida tiene tope (`256 KiB` por read, `500` entradas por list) y avisa si trunca.
- `git.status/log/diff` rechazan flags con capacidad de escritura (`--output`, `-o`):
  un subcomando de lectura nivel A no puede escribir a disco.
- Nada de esto journala (no hay mutación que deshacer).

## Qué requiere qué

- **Directo (A):** solo lecturas / inspección / creación en sandbox controlado.
- **Confirmación normal (B):** mover/renombrar, registrar finanza.
- **Confirmación fuerte (C):** escribir/crear/borrar, shell allowlisted, git commit/push, instalar.
- **Siempre rechazado (D):** la tabla de denylist.
- **Solo sandbox:** ejecución de código no confiable, pruebas del propio Wyss.
- **Backup previo:** overwrite de archivo existente ya captura backup (`capture_overwrite_backup`).

## Modelo de red / móvil (LAN)

- **Bind opt-in:** sin `wyss web --lan`, nada escucha fuera de `127.0.0.1`.
- **Host/Origin allowlist exacta:** con `--lan` solo se aceptan `127.0.0.1`, `localhost`
  y el IP LAN detectado; cualquier otro Host → 403 (anti DNS-rebinding).
- **Origin `null` (browsers reales):** Chrome Android con cert self-signed aceptado
  serializa `Origin: null` en POSTs same-origin. Se acepta SOLO con
  `Sec-Fetch-Site: same-origin` (header prohibido, no forjeable por JS); un iframe
  sandboxeado o un POST cross-site llegan con `cross-site`/`nested` → 403, y sin la
  cookie SameSite=Strict → 401 antes. Un Origin explícito inválido manda siempre
  (403 aunque Sec-Fetch mienta). Los rechazos del middleware quedan logueados.
- **Auth:** token 32B urlsafe (`compare_digest`) → cookie HttpOnly SameSite=Strict;
  401 en TODO path sin auth. No hay envío de comandos sin autenticar.
- **El bridge nunca decide riesgo:** solo reenvía al daemon, que re-evalúa.
- **TLS opt-in (PR-10):** `wyss web --tls` sirve HTTPS con cert self-signed
  auto-generado (`data/tls/`, openssl del sistema, SAN = localhost + IP LAN,
  clave 0600). La cookie del token lleva `Secure` y el Origin permitido pasa a
  `https://` (un solo esquema, el servido). La CLI imprime la huella SHA-256 para
  verificar el cert en el teléfono antes de aceptarlo (TOFU); cero avisos =
  traer certs de mkcert a `data/tls/` (se usan tal cual si cubren los hosts).
  Si cambia la IP LAN (DHCP), el cert se regenera solo.
- **Residual conocido:** el primer accept del cert self-signed es TOFU — un MITM
  activo EN la LAN durante ese primer pairing podría interponer su cert; la
  huella impresa existe para eso. mkcert elimina el aviso pero exige instalar su
  CA en el teléfono (paso manual equivalente).

## Undo / rollback

El journal (`undo_entries`) registra la operación inversa antes de mutar; el rollback
automático corre en ABORT intra-plan. `wyss undo <task_id>` (PR-09) deshace las
mutaciones ya aplicadas: lista las entradas `applied` en orden inverso, corre
pre-chequeos de colisión (dry-run con `--dry-run`), evalúa el plan inverso con el
MISMO policy engine (una inversa en denylist → undo rechazado; NO es un bypass),
pide la palabra del nivel resultante y aplica abortando en el primer fallo. Cada
entrada revertida pasa a `rolled_back` (segundo undo = nada que deshacer). Todo
queda auditado (`command.received` → `confirmation.answered` → `task.completed/failed`).
Shell y git no se deshacen (irreversibles por diseño; el journal no los registra).

## Huecos conocidos (documentados, no silenciados)

- `shell-privilege-escalation` y `shell-rm-bypass` matchean el NOMBRE del binario
  (`sudo`, `rm`), no la ruta absoluta (`/usr/bin/sudo`). El ShellAdapter usa nombres y
  la allowlist vacía cubre el resto; endurecer a rutas si se puebla la allowlist con
  paths absolutos.
- `systemctl stop <servicio-no-firewall>` sigue siendo C + allowlist fail-closed, no D:
  parar un servicio propio (docker, n8n) es un uso legítimo bajo confirmación fuerte.
  El "salvo política explícita" del scope lo implementa la allowlist (vacía = todo
  bloqueado; poblarla ES la política explícita).
- `shell-perm-destructive` matchea `chmod -r*` en minúsculas: bloquea también
  `chmod -R 755` (recursivo no-777). Over-blocking asumido: recursivo sobre permisos
  es destructivo por alcance, no solo por modo.
- No existe tipo de acción de red (`net.*`): una exfiltración por red sería `shell.run`
  (allowlist) o un tipo desconocido (C). Formalizar en v0.2 si se agrega capacidad de red.
