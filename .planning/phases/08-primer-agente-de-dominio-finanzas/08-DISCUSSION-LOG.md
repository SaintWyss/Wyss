# Phase 8: Primer Agente de Dominio (Finanzas) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 8-Primer Agente de Dominio (Finanzas)
**Areas discussed:** Identidad del agente, BC + datos reales, Las 3 tareas de aceptación, Presupuesto + enforcement, Rumbo de la fase (re-scope), Carga de datos, Estructura del roadmap

---

## Identidad del agente

| Option | Description | Selected |
|--------|-------------|----------|
| Pellegrini | Carlos Pellegrini fundó el Banco de la Nación Argentina — alineado con finanzas | ✓ |
| Mitre | Prócer genérico, sin vínculo financiero | |
| Roca | Prócer, asociado a expansión económica s.XIX | |

**User's choice:** Pellegrini
**Notes:** `agent_id="pellegrini"`, `domain="finanzas"`.

---

## BC + datos reales

| Option | Description | Selected |
|--------|-------------|----------|
| Finanzas personales | Docs propios (resúmenes tarjeta, planillas) | |
| RAGcorp | BC corporativa | |
| Necesito definirlo | Charlarlo antes de fijar | ✓ |

**User's choice:** "Necesito definirlo" → luego reveló: solo tiene fotos de recibos (no se usan), no subió gastos, pero puede *decir* cuánto ingresa/gasta. Quiere "ayudarme a ser económicamente estable".
**Notes:** Esto invalidó el modelo de agente-sobre-documentos. No hay corpus para indexar. El requerimiento real es un coach que registra y asesora.

---

## Rumbo de la fase (re-scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Pellegrini coach sobre notas tuyas | Owner mantiene notas markdown como BC | |
| Cambiar a estudio (Belgrano) | Arrancar donde sí hay datos reales hoy | |
| Coach con registro de gastos real | Agente registra transacciones (capacidad nueva) | ✓ |

**User's choice:** Coach con registro de gastos real.
**Notes:** El owner quiere el agente de verdad — que registre ingresos/gastos y asesore, no un RAG sobre documentos inexistentes. Re-escala la fase: requiere una capacidad ledger nueva.

---

## Carga de datos (interfaz del ledger)

| Option | Description | Selected |
|--------|-------------|----------|
| Conversándole al agente | "gasté 5000 en super" → agente registra | |
| Comando CLI | `wyss fin add-gasto 5000 super`, determinístico | |
| Ambos | CLI + conversacional | ✓ |

**User's choice:** Ambos.
**Notes:** CLI para precisión, conversacional para comodidad. La escritura conversacional (`finance.record`) pasa por el policy engine (owner-instruida, no desde BC).

---

## Estructura del roadmap

| Option | Description | Selected |
|--------|-------------|----------|
| Una Fase 8 MVP | Ledger + Pellegrini como slice vertical único | ✓ |
| Partir en dos fases | Fase 8 ledger, Fase 8.x agente encima | |

**User's choice:** Una Fase 8 MVP.
**Notes:** Vertical slice coherente, entrega algo usable E2E.

---

## Presupuesto + enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| economico + $5 | Tope chico, prueba el gate rápido | ✓ (decisión Claude) |
| economico + $10 | Más margen | |
| fuerte + $15 | Razonamiento profundo, caro | |

**User's choice:** El owner no entendía qué era el presupuesto ("no entiendo para qué son los costos"). Se aclaró: es el tope de gasto del *agente en llamadas a modelos de IA* (no la plata del owner). Decisión técnica delegada a Claude → `economico + $5`.
**Notes:** Hallazgo: el enforcement per-agente YA existe en `gateway/cost.py`; falta solo cablear `agent_budgets` desde config.

---

## Claude's Discretion

- Esquema SQLite del ledger, columnas, índices.
- Action types del ledger (`finance.record`/`finance.query`) y su nivel en la denylist.
- Forma de los subcomandos CLI y salida Rich.
- Patrón de lectura del ledger por Pellegrini (tool inyectado vs. retrieval adaptado).
- Presupuesto + tier (economico + $5).

## Deferred Ideas

- Belgrano (dominio estudio) — segundo agente, datos reales disponibles (UTN/Notion).
- OCR de recibos / ingesta de extractos bancarios.
- Categorización inteligente de gastos (vs. free-text).
- Hermes orquestador real (desbloquear 05-05).
