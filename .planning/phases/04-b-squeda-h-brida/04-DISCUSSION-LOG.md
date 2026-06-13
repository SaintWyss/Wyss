# Phase 4: Búsqueda Híbrida - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 4-Búsqueda Híbrida
**Areas discussed:** Salida del CLI search, Degradación sin vectores, Eval set dorado, Alcance BC + frescura

**Mode:** Advisor (research-backed comparison tables, 4 parallel gsd-advisor-researcher agents on sonnet, calibration tier: standard)

---

## Salida del CLI `wyss search`

| Option | Description | Selected |
|--------|-------------|----------|
| Panels + --json | Rich Panels verticales por hit + --json para n8n/scripts + auto-JSON al detectar pipe. --limit 10 default. | ✓ |
| Table compacta | Una fila por hit; scannable pero trunca rutas y extractos. | |
| Grep-style plano | Texto plano pipe-friendly, sin estructura visual. | |

**User's choice:** Panels + --json (opción recomendada)
**Notes:** rich ya es dep declarada y usada en cli.py; KNOW-05 se expresa mejor en bloques verticales; n8n/Hermes consumirán JSON.

---

## Degradación sin vectores

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-fallback + aviso | FTS5-only automático con banner + campo degraded en JSON + exit 0 + flag --fts-only. | ✓ |
| Auto-fallback + exit 2 | Igual pero exit code 2 para pipelines. Contradice D-38. | |
| Fallo duro sin --fts-only | Sin Ollama la búsqueda falla salvo flag explícito. Rompe criterio 3. | |

**User's choice:** Auto-fallback + aviso (opción recomendada)
**Notes:** Espejo de D-32 (ingesta). El researcher sugirió exit code 2; descartado por conflicto con precedente D-38 (exit 0 = corrida completó).

---

## Eval set dorado (AUD-03)

| Option | Description | Selected |
|--------|-------------|----------|
| A: sintético CI duro | Corpus fixture commiteado + FakeEmbedding + hit@1, gate duro, N=20. | ✓ |
| D: híbrido A + curado local | A en CI + set curado por el owner (N=50, MRR@5) corrido localmente con Ollama. | |
| B: curado por owner | Owner cura 20-30 queries reales, corpus anonimizado, hit@5. | |

**User's choice:** A: sintético CI duro (opción recomendada)
**Notes:** Restricción dura: CI sin Ollama ni los 2 TB. Espejo de POL-06. El set curado local quedó como deferred (extensión aditiva, Fase 5+).

---

## Alcance BC + frescura

| Option | Description | Selected |
|--------|-------------|----------|
| Todas las BC + footer y status | Default todas, --kb acota. Footer 1 línea en cada search + wyss status detallado. Query centralizada en service. | ✓ |
| Todas las BC + solo status | Search limpio sin footer; frescura solo en wyss status. | |
| --kb obligatorio + ambos | Cada search exige BC explícita. Más fricción. | |

**User's choice:** Todas las BC + footer y status (opción recomendada)
**Notes:** Wildcard se expande en service layer; el port Retrieval siempre recibe kb_ids explícitos — sin deuda hacia Fase 7.

---

## Claude's Discretion

- Parámetros RRF (k, pesos) con defaults en config.toml
- Esquema JSON de salida
- Umbral hit@1 y composición del corpus fixture
- Fecha por resultado (mtime vs fecha de indexación)
- Detalle del comando `wyss status`
- Piloto automático heredado de Fase 3 para decisiones menores

## Deferred Ideas

- Set de eval curado por el owner sobre archivos reales (N=50, MRR@5, local con Ollama) — Fase 5+
