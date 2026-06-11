# Phase 2: Gateway de Modelos - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 2-Gateway de Modelos
**Areas discussed:** Proveedores reales, Routing costo/complejidad, Presupuesto/gate, Minimizer + tracing, Streaming, Cálculo de costo, Timeouts y retries, Identidad del request

---

## Proveedores reales

| Option | Description | Selected |
|--------|-------------|----------|
| LiteLLM + Anthropic | LiteLLM local (económico, ya corriendo) + Anthropic directo (fuerte) | ✓ |
| LiteLLM + Ollama | Todo local/barato, sin API Anthropic | |
| Anthropic + OpenAI directos | Sin dependencia de LiteLLM | |

**User's choice:** LiteLLM + Anthropic

| Option | Description | Selected |
|--------|-------------|----------|
| Ollama local | Embeddings locales, archivos nunca salen | ✓ |
| Vía LiteLLM | Un solo punto de salida, contenido viaja a cloud | |
| OpenAI embeddings | Calidad probada, segunda API key | |

**User's choice:** Ollama local (EmbeddingProvider)

---

## Routing costo/complejidad

| Option | Description | Selected |
|--------|-------------|----------|
| Tiers por config, caller elige | config.toml define tiers; caller declara tier; determinístico | ✓ |
| Reglas determinísticas en router | Router clasifica solo por heurísticas | |
| LLM clasifica complejidad | Modelo barato decide tier | |

**User's choice:** Tiers por config, caller elige

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-fast, sin fallback | Error claro auditado; sin cambio de tier silencioso | ✓ |
| Retry mismo proveedor | Backoff en transientes, nunca cambia tier | |
| Fallback automático de tier | Máxima disponibilidad, gasto impredecible | |

**User's choice:** Fail-fast sin fallback (nota: el retry de transientes se decidió aparte en ronda 2 — D-25)

---

## Presupuesto/gate

| Option | Description | Selected |
|--------|-------------|----------|
| Global mensual + por-agente | Ambos en config, gate chequea ambos pre-llamada | ✓ |
| Solo global mensual | Más simple, riesgo agente glotón | |
| Por-tarea + global | Requiere estimación por tarea (Fase 5+) | |

**User's choice:** Global mensual + por-agente

| Option | Description | Selected |
|--------|-------------|----------|
| Editar config + reload | Decisión humana explícita, auditada; sin override | ✓ |
| Comando admin explícito | Path de override a proteger aparte | |
| Reset automático al cambiar mes | Sin válvula de escape | |

**User's choice:** Editar config + reload

---

## Minimizer + tracing

| Option | Description | Selected |
|--------|-------------|----------|
| Bloquear llamada | Fail-closed; secreto en prompt = bug upstream | ✓ |
| Redactar y enviar | Fluido pero normaliza secretos en el borde | |
| Redactar + warning auditado | Punto medio, leak posible | |

**User's choice:** Bloquear llamada

| Option | Description | Selected |
|--------|-------------|----------|
| Valores de .env + patrones | Secretos reales + regex built-in + config aditiva | ✓ |
| Solo patrones regex | Ciego a secretos sin formato estándar | |
| Solo valores de .env | Ciego a secretos fuera de .env | |

**User's choice:** Valores de .env + patrones

| Option | Description | Selected |
|--------|-------------|----------|
| Completos, SQLite propio | traces.db separada, prompts completos post-minimizer, retención 90d | ✓ |
| Truncados, SQLite propio | Liviano pero pierde el dato al debuggear | |
| Completos, misma DB de audit | Mezcla retención forever con expirable | |

**User's choice:** Completos, SQLite propio

---

## Ronda 2 — Streaming

| Option | Description | Selected |
|--------|-------------|----------|
| No — respuesta completa | ask_stream() aditivo si Fase 5 lo pide (regla #9) | ✓ |
| Sí — streaming ahora | Minimizer/tracing sobre streams mucho más complejos | |

**User's choice:** No — respuesta completa

## Ronda 2 — Cálculo de costo

| Option | Description | Selected |
|--------|-------------|----------|
| Tabla local de precios | tokens × precio en config; determinístico para todo provider | ✓ |
| Lo que reporte el provider | Dos fuentes de verdad, gate depende de terceros | |

**User's choice:** Tabla local de precios

## Ronda 2 — Timeouts y retries internos

| Option | Description | Selected |
|--------|-------------|----------|
| Retry transientes + timeout config | 2 retries backoff solo timeout/429/5xx mismo provider; 120s default; re-pasa gate | ✓ |
| Cero retries | Blip de red mata tareas largas | |
| Retries agresivos | Esconde problemas reales | |

**User's choice:** Retry transientes + timeout config

## Ronda 2 — Identidad del request

| Option | Description | Selected |
|--------|-------------|----------|
| agent_id+task_id+tier+purpose | Traces consultables por tipo de uso | ✓ |
| Solo lo actual + tier | Mínimo para routing/presupuesto | |
| Trace jerárquico completo | OpenTelemetry-style, overkill hasta Fase 9 | |

**User's choice:** agent_id+task_id+tier+purpose

## Claude's Discretion

- Esquema exacto de tablas traces.db
- Naming de aliases de tiers/modelos y estructura interna de `gateway/`
- Set inicial de regex built-in de secretos
- Mecánica del fixture "secreto trampa"
- Librería HTTP/SDK por provider (httpx vs SDK oficial)

## Deferred Ideas

- `ask_stream()` streaming aditivo — Fase 5 si la CLI lo necesita
- Trace jerárquico parent_trace_id/span — Fase 9 (multi-agente)

## Nota de proceso

Usuario pidió chunks cortos con checkpoint para poder pausar/retomar entre áreas — se guardó 02-DISCUSS-CHECKPOINT.json tras cada área (eliminado al escribir CONTEXT.md).
