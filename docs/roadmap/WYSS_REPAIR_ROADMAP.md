# Wyss — Repair Roadmap

> 2026-07-02. No es el roadmap de producto (ese vive en `.planning/ROADMAP.md`, fases 9-10 pendientes).
> Es el camino de reparación/estabilización previo a retomar feature work. Convención de ejecutores del
> repo (CLAUDE.md): **Claude = juicio · Codex (`codex-gsd-exec`) = construcción · Gemini = acarreo**.

## Orden y dependencias

```
F1 (PR-00 baseline) ──► F2 (PR-01 CI) ──► F3 (PR-03 config) ──► F4 (DECISIÓN owner) ──► F5 (PR-06 orquestador LLM)
                                                                                    └──► F6 (calibración advisory)
F7 (PR-09 docs) — paralelo desde F2
F8 (PR-08 security re-audit) — después de F5
F9 (PR-07 UX pass) — después de F5
F10 (PR-10 release candidate v0.1) — último; luego recién fase 9 GSD
```

| Fase | PR | Por qué / razón | Depende de | Riesgo | Complejidad | Executor |
|---|---|---|---|---|---|---|
| F1 | PR-00 baseline | Partir de estado limpio y etiquetado; higiene data/ y gitignore | — | Nulo | Trivial | Claude Code directo (no amerita Codex) |
| F2 | PR-01 CI | Único fix P0 barato: la cadena verde pasa de convención a gate automático antes de delegar nada a modelos baratos | F1 | Bajo (runner sin NTFS: tests ntfs ya se auto-skipean) | Baja | Codex vía `codex-gsd-exec`; review Claude |
| F3 | PR-03 config | Podar deps muertas; `.env` real; sin esto ningún provider corre | F1 | Bajo | Baja | Codex; secretos los pone el owner a mano (jamás un agente) |
| F4 | Decisión orquestador | Hermes (local, bloqueado) vs `LLMOrchestrator` vía gateway (recomendado). Cambia el alcance de F5 | F3 | — | — | **Owner + Fable 5** (decisión de arquitectura — no delegable) |
| F5 | PR-06 orquestador LLM | Cierra el gap #1 del producto: `ask` con LLM real detrás de policy | F4 | Medio (parsing LLM→Plan; mitigado fail-closed) | Media-alta | Plan: Fable 5 · construcción: Codex · gates: Claude |
| F6 | Calibración advisory | Deuda diferida 08-04: prosa de Pellegrini nunca evaluada con LLM real | F3 (LiteLLM up) | Bajo | Baja | Claude (juicio de calidad); script throwaway ya descrito en STATE.md |
| F7 | PR-09 docs | README/CLAUDE.md/docs falsos desorientan a todo ejecutor futuro | F2 | Nulo | Baja | Draft: Gemini (acarreo) · verificación factual: Claude |
| F8 | PR-08 security re-audit | Confirmar mitigaciones fases 6-8 (traversal/symlink) con el path LLM ya cableado | F5 | Bajo | Media | Fable 5 (`/gsd-secure-phase`) — juicio, no delegable a baratos |
| F9 | PR-07 UX CLI | Errores, empty states, consistencia de idioma — pulido pre-RC | F5 | Nulo | Baja | Codex; criterio UX: Claude (memoria: UX no se delega a Codex) |
| F10 | PR-10 RC v0.1 | Corte de scope: qué entra a v0.1, tag, systemd unit, smoke E2E | F5-F9 | Medio (decisiones de corte) | Media | Owner + Fable 5; mecánica: Claude Code |

## Criterios de aceptación por fase (resumen — detalle en cada PR-SPEC)

- **F1**: `git status` limpio; data/ sin residuos de test; tag `audit-baseline-2026-07-02`.
- **F2**: push a main dispara workflow que corre la cadena completa y falla si algo rompe.
- **F3**: `uv sync` sin fastmcp/mcp; `wyss status` reporta provider configurado; `.env` presente (no commiteado).
- **F5**: `wyss ask "creá un archivo de prueba en X"` → plan generado por LLM real → confirmación B → ejecución → auditado → undo posible.
- **F6**: 3 tareas D-87 evaluadas con LLM-judge real, score documentado.
- **F7**: README refleja estado real; CLAUDE.md §Architecture poblado; docs/00-18 con banner histórico.
- **F10**: tag `v0.1.0-rc1`; smoke E2E documentado y corrido en ambas PCs (Santiago-PC y Acer).

## Qué NO está en este roadmap (deliberado)

- Reestructuración de paquetes / renombres — la estructura está sana y enforced; churn sin retorno.
- Refactor de `bootstrap/cli.py` — 35.6K es tolerable para un composition root+CLI; solo si duele al agregar fase 9.
- Fases 9-10 de producto — retoman por GSD (`/gsd-discuss-phase 09`) DESPUÉS de F10.
