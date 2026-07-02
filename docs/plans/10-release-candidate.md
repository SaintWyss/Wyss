# PR-10 — Release candidate v0.1

## 1. Objective
Cortar y etiquetar `v0.1.0-rc1`: definición explícita de qué entra, smoke E2E documentado, daemon operable como servicio. Después de esto — y solo después — retomar feature work (fase 9 GSD).

## 2. Context from the audit
40/41 planes ejecutados pero no existe definición de "release": ni tag, ni criterio de usable-diario, ni systemd unit (STACK.md la promete: `~/.config/systemd/user/wyss.service`). Sin corte explícito, la fase 9 (multi-agente) y la 10 (Modo Equipo — otro producto) pueden arrancar sobre un core loop sin cerrar.

## 3. Exact problem
"Terminado" no está definido. El audit lo define: v0.1 = un owner usa Wyss todos los días para buscar, registrar finanzas y pedir acciones por lenguaje natural con confirmación — en sus dos PCs.

## 4. Architectural decision
**Entra a v0.1**: índice+búsqueda (F3-4), daemon+policy+bandeja (F5 parcial), ejecución con undo (F6), agentes config-driven (F7), Pellegrini+ledger (F8), LLMOrchestrator (PR-06), advisory calibrada.
**Sale de v0.1**: Hermes local (adapter futuro), fase 9 (multi-agente/rutinas → v0.2), fase 10 (Modo Equipo → producto aparte), móvil/marketplace (README fase 7 histórica).

## 5. Files to read first
- Todos los PR-SPECs previos (deben estar mergeados: 00, 01, 03, 06, 07, 09; 08 ejecutado)
- `.planning/STATE.md` (deudas diferidas — la calibración advisory debe estar cerrada)
- `config/config.example.toml`

## 6. Files allowed to modify
- `scripts/wyss.service` (NUEVO — systemd user unit) + `scripts/install-service.sh` (NUEVO, opcional)
- `docs/RELEASE-v0.1.md` (NUEVO — smoke checklist + qué entra/sale)
- `pyproject.toml` (version → `0.1.0rc1`)
- `README.md` (sección instalación/servicio)

## 7. Files forbidden to modify
- `src/` — un RC no agrega features. Cualquier bug hallado por el smoke = PR aparte antes del tag.

## 8. Required changes
1. `scripts/wyss.service`: systemd user unit (ExecStart=`uv run wyss start` con WorkingDirectory al repo, Restart=on-failure, journal logging) + instrucciones de instalación (`systemctl --user enable --now wyss`).
2. `docs/RELEASE-v0.1.md`: alcance (§4) + smoke E2E de 10 pasos: index sobre carpeta real → search con hit → status → start (servicio) → ask (plan LLM real) → confirm → verificación del efecto → undo → fin add-gasto/ver → audit del camino completo.
3. Correr el smoke en Santiago-PC Y en la Acer; anotar resultados (fecha/máquina) en el doc.
4. Version bump + tag anotado `v0.1.0-rc1`.

## 9. Contracts and invariants
- Cadena verde + CI verde en el commit del tag.
- El smoke se corre con LLM real (no fakes) y presupuesto activo.

## 10. Tests required
```bash
uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
systemctl --user status wyss   # activo en ambas máquinas
```

## 11. Manual verification
El smoke E2E completo ES la verificación manual; owner firma cada paso en RELEASE-v0.1.md.

## 12. Risks
- La Acer tiene Docker/autostart apagados y menos RAM — el smoke puede revelar asunciones de recursos. Eso es exactamente lo que el RC debe detectar.
- Presión de meter "una cosita más" antes del tag → el alcance §4 es cerrado; lo nuevo va a v0.2.

## 13. Rollback plan
`git tag -d v0.1.0-rc1` + revert del bump. El servicio se desinstala con `systemctl --user disable --now wyss`.

## 14. Acceptance criteria
- Tag `v0.1.0-rc1` sobre commit con CI verde.
- Smoke firmado en ambas PCs.
- `scripts/wyss.service` instalado y activo.
- RELEASE-v0.1.md define v0.2 (fase 9) como siguiente milestone GSD.

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. NO commitees. PROHIBIDO tocar src/.
Prerequisito (verificalo y abortá si falla): git log muestra mergeados los PRs 00,01,03,06,07,09 y
uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports está verde.

1. Crea scripts/wyss.service: systemd USER unit. [Unit] Description=Wyss daemon. [Service]
   Type=simple, WorkingDirectory=/mnt/hdd/Data/10_Workspace/projects/wyss,
   ExecStart=/usr/bin/env uv run wyss start, Restart=on-failure, RestartSec=5.
   [Install] WantedBy=default.target. Comentario cabecera: instalar con
   ln -s o cp a ~/.config/systemd/user/ + systemctl --user daemon-reload + enable --now wyss.
2. Crea docs/RELEASE-v0.1.md con: alcance IN (índice, búsqueda, daemon+policy+bandeja, ejecución+undo,
   agentes config-driven, Pellegrini+ledger, LLMOrchestrator calibrado) / OUT (Hermes, fase 9 rutinas,
   fase 10 Modo Equipo, móvil) y checklist smoke E2E de 10 pasos (index→search→status→servicio→ask con
   LLM real→confirm→verificar efecto→undo→fin→audit) con columnas para firmar fecha/resultado en
   Santiago-PC y Acer.
3. pyproject.toml: version = "0.1.0rc1" (solo esa línea).
4. README.md: sección corta "Correr como servicio" apuntando a scripts/wyss.service.
NO corras el smoke ni crees el tag (los hace el owner). SUMMARY: archivos creados + diff de pyproject.
```
