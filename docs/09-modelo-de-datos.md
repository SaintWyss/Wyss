# Wyss — Modelo de Datos Preliminar

**Versión:** 0.1

---

## 1. Entidades principales

```text
Owner
- id
- name
- created_at

Context (organización / área de vida)
- id
- owner_id
- name                  -- "Personal", "RAGcorp", "Beca Ciberseguridad", "Cliente X"
- type                  -- personal | empresa | proyecto
- created_at

Worker
- id
- context_id
- name
- role
- contact_channel       -- mensajería, email
- active

Agent
- id
- owner_id
- name                  -- identidad propia (ej. nombres argentinos)
- domain                -- estudio | organización | finanzas | seguimiento | ...
- base_model_version    -- versión del modelo base del que se instanció
- assigned_ai_model     -- alias en el gateway
- budget_limit
- status                -- active | suspended | retired
- created_at

KnowledgeBase
- id
- context_id
- name
- source_type           -- carpeta local | RAG externo | base documental
- location
- sensitivity_level
- indexed_at

KnowledgeSource
- id
- knowledge_base_id
- path
- media_type
- size_bytes
- last_modified
- index_status

IndexEntry
- id
- knowledge_source_id
- chunk_ref
- metadata_json
- fts_ref               -- referencia al índice full-text
- vector_ref            -- referencia al índice vectorial
- summary

Permission (Habilitación)
- id
- granted_by            -- owner (vía orquestador)
- subject_type          -- agent | worker
- subject_id
- knowledge_base_id
- access_level          -- read | read_write
- valid_from
- valid_until
- revoked

Task
- id
- owner_id
- agent_id              -- null si la resuelve el orquestador
- raw_command
- intent
- status                -- received | planned | waiting_confirmation | executing | done | failed | rejected
- created_at

Plan
- id
- task_id
- summary
- steps_json
- risk_level            -- A | B | C | D
- requires_confirmation
- rejected
- rejection_reason

Action
- id
- plan_id
- type
- target
- parameters_json
- status
- verification_result

Routine
- id
- owner_id
- agent_id
- name
- trigger               -- cron / evento
- definition_json
- active
- last_run_at

ToolInvocation
- id
- action_id
- tool_name
- model_alias           -- si usó IA
- tokens_in / tokens_out
- cost_estimate
- status

Confirmation
- id
- plan_id
- level                 -- simple | fuerte
- prompt
- owner_response
- confirmed_at

PolicyDecision
- id
- plan_id
- decision              -- allow | confirm_simple | confirm_strong | reject
- risk_level
- rationale
- created_at

AuditLog
- id
- task_id
- actor_type            -- owner | orchestrator | agent | worker
- actor_id
- event_type
- message
- metadata_json
- created_at
```

## 2. Relaciones clave

```text
Owner 1───N Context
Context 1───N KnowledgeBase
Context 1───N Worker
Owner 1───N Agent
KnowledgeBase 1───N KnowledgeSource 1───N IndexEntry
Agent N───N KnowledgeBase        (vía Permission)
Worker N───N Agent               (vía Permission/asignación)
Task 1───1 Plan 1───N Action 1───N ToolInvocation
Plan 1───1 PolicyDecision
Plan 0───1 Confirmation
Owner 1───N Routine
Todo ───► AuditLog
```

## 3. Reglas de integridad

1. Un `Agent` sin `Permission` vigente sobre una `KnowledgeBase` no puede leerla — sin excepciones.
2. Un `Plan` con `risk_level = D` siempre tiene `rejected = true` y nunca genera `Action`.
3. Un `Plan` con `requires_confirmation = true` no genera `Action` sin `Confirmation` registrada.
4. Toda `Action` ejecutada referencia al menos un evento en `AuditLog`.
5. Las `KnowledgeBase` de un `Context` jamás son visibles desde otro `Context` salvo habilitación explícita del owner.
6. `Permission` es revocable en cualquier momento y la revocación es inmediata.
