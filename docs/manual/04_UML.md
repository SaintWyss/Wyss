# 04 — Diagramas UML

## Propósito

Yo uso UML para separar cuatro preguntas: quién usa Wyss, qué partes lo forman, cómo se comunican y qué estados atraviesa una tarea. Los diagramas están en Mermaid para revisión dentro de GitHub.

## Cobertura UML 2

| Tipo | Cobertura | Aplicación |
|---|---|---|
| casos de uso | incluida | owner, automatización externa y provider |
| clases | incluida | plan, acción, política y resultados |
| objetos | incluida | propuesta pendiente concreta |
| componentes | incluida | capas y adaptadores |
| paquetes | incluida | dependencias hexagonales |
| estructura compuesta | incluida | interior del daemon |
| despliegue | incluida | PC, teléfono, provider y servicios |
| actividad | incluida | loop ask-to-audit |
| estados | incluida | ciclo de una tarea/propuesta |
| secuencia | incluida | ask y confirm |
| comunicación | incluida | mensajes entre colaboradores |
| visión general de interacción | incluida | productores de planes |
| temporal | incluida | TTL y re-evaluación |
| perfil | incluida | estereotipos de criticidad |

## 1. Casos de uso

```mermaid
flowchart LR
    O[Owner]
    N[n8n / sistema externo]
    L[Proveedor LLM]
    T[Teléfono / APK]

    O --> A((Pedir una tarea))
    O --> B((Confirmar o rechazar))
    O --> C((Buscar conocimiento))
    O --> D((Programar rutinas))
    O --> E((Gestionar memoria))
    O --> F((Consultar digest y finanzas))
    O --> G((Deshacer cambios compatibles))
    T --> A
    T --> B
    N --> H((Proponer intake externo))
    L --> I((Clasificar y proponer plan))
    I --> A
```

## 2. Clases de dominio

```mermaid
classDiagram
    class Task {
      +taskId
      +instruction
    }
    class Plan {
      +taskId
      +summary
      +steps
      +rationale
      +estimatedRisk
    }
    class Action {
      +type
      +target
      +parameters
      +onError
    }
    class PolicyDecision {
      +riskLevel
      +outcome
      +matchedRules
      +reasons
    }
    class PendingProposal {
      +id
      +planJson
      +riskLevel
      +status
      +expiresAt
    }
    class ToolResult {
      +success
      +detail
      +payload
    }
    class AuditEvent {
      +actor
      +eventType
      +message
      +payload
    }
    class MemoryFact {
      +category
      +value
      +tier
      +source
    }
    class Routine {
      +schedule
      +planJson
      +status
      +lastOutcome
    }

    Task --> Plan
    Plan "1" --> "*" Action
    Plan --> PolicyDecision
    PolicyDecision --> PendingProposal
    Action --> ToolResult
    Plan --> AuditEvent
    Routine --> Plan
    MemoryFact ..> Plan : contexto como dato
```

## 3. Objetos de una propuesta

```mermaid
flowchart LR
    P[plan: Plan<br/>taskId=t-42<br/>steps=1]
    A[action: Action<br/>type=file.delete<br/>target=/tmp/demo]
    D[decision: PolicyDecision<br/>risk=C<br/>outcome=CONFIRM]
    Q[pending: PendingProposal<br/>status=pending<br/>TTL=24h]

    P --> A
    P --> D
    D --> Q
```

## 4. Componentes

```mermaid
flowchart TB
    CLI[CLI Typer]
    WEB[FastAPI bridge + React]
    APK[Capacitor Android]
    DAEMON[Daemon JSON-RPC]
    ORCH[Deterministic / LLM Orchestrator]
    POLICY[CognitivePolicyEngine]
    PENDING[PendingStore]
    SCHED[RoutineScheduler]
    EXEC[PlanExecutor]
    TOOLS[File / Shell / Git / Notion / Memory]
    GATE[Model Gateway]
    KNOW[Knowledge Retrieval]
    AUDIT[Audit DB]

    CLI --> DAEMON
    WEB --> DAEMON
    APK --> WEB
    DAEMON --> ORCH
    ORCH --> GATE
    ORCH --> KNOW
    DAEMON --> POLICY
    DAEMON --> PENDING
    SCHED --> DAEMON
    DAEMON --> EXEC
    EXEC --> TOOLS
    DAEMON --> AUDIT
```

## 5. Paquetes y dependencia

```mermaid
flowchart LR
    BOOT[bootstrap]
    CORE[core]
    ORC[orchestrator]
    AG[agents]
    KN[knowledge]
    GW[gateway]
    EX[execution]
    AU[audit]
    LE[ledger]
    ME[memory]
    NO[notion]

    BOOT --> CORE
    BOOT --> ORC
    BOOT --> AG
    BOOT --> KN
    BOOT --> GW
    BOOT --> EX
    BOOT --> AU
    BOOT --> LE
    BOOT --> ME
    BOOT --> NO

    ORC --> CORE
    AG --> CORE
    KN --> CORE
    GW --> CORE
    EX --> CORE
    AU --> CORE
    LE --> CORE
    ME --> CORE
    NO --> CORE
```

Las capas laterales no deben importarse entre sí; bootstrap las conecta.

## 6. Estructura compuesta del daemon

```mermaid
flowchart TB
    subgraph DaemonServer
      RPC[JSON-RPC dispatcher]
      ASK[ask handler]
      CONF[confirm handler]
      ROUT[routine handlers]
      MEM[memory handlers]
      DIG[digest handler]
      INT[intake handler]
      ENG[Policy engine]
      PEN[Pending store]
      RUN[Plan runner]
      LOG[Audit]
    end

    RPC --> ASK
    RPC --> CONF
    RPC --> ROUT
    RPC --> MEM
    RPC --> DIG
    RPC --> INT
    ASK --> ENG
    CONF --> ENG
    ASK --> PEN
    CONF --> PEN
    ASK --> RUN
    CONF --> RUN
    ASK --> LOG
    CONF --> LOG
```

## 7. Actividad del loop principal

```mermaid
flowchart TD
    A[Recibir instrucción] --> B[Auditar comando]
    B --> C[Clasificar intención]
    C --> D{¿ambigua?}
    D -- sí --> E[Pedir aclaración]
    D -- no --> F[Crear plan]
    F --> G[Evaluar política]
    G --> H{Nivel/outcome}
    H -- D/reject --> I[Rechazar y auditar]
    H -- A/execute --> J[Ejecutar]
    H -- B/C --> K[Persistir pendiente]
    K --> L[Owner confirma o rechaza]
    L --> M[Re-evaluar política]
    M --> N{¿sigue permitido?}
    N -- no --> I
    N -- sí --> J
    J --> O[Verificar resultado]
    O --> P[Auditar terminal]
```

## 8. Máquina de estados de propuesta

```mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Rejected: nivel D
    Proposed --> Executing: nivel A
    Proposed --> Pending: nivel B/C
    Pending --> Expired: TTL
    Pending --> Rejected: owner rechaza
    Pending --> Rejected: re-evaluación D
    Pending --> Executing: confirmación válida
    Executing --> Completed: verificación exitosa
    Executing --> Failed: ejecución/verificación falla
    Completed --> UndoPlanned: owner solicita undo
    UndoPlanned --> Completed: no confirma
    UndoPlanned --> Reverted: inversa aprobada y exitosa
    UndoPlanned --> Failed: inversa falla
```

## 9. Secuencia `ask`

```mermaid
sequenceDiagram
    actor O as Owner
    participant C as CLI/Web
    participant D as Daemon
    participant R as Orchestrator
    participant P as Policy
    participant S as PendingStore
    participant X as PlanExecutor
    participant A as Audit

    O->>C: instrucción
    C->>D: ask
    D->>A: COMMAND_RECEIVED
    D->>R: classify + draft
    R-->>D: Plan
    D->>A: PLAN_CREATED
    D->>P: evaluate(plan)
    P-->>D: decision
    alt A
      D->>X: run(plan)
      X-->>D: result
    else B/C
      D->>S: save(plan, TTL)
      S-->>D: pending_id
    else D
      D-->>C: rejected
    end
    D-->>C: resultado
```

## 10. Secuencia `confirm`

```mermaid
sequenceDiagram
    actor O as Owner
    participant C as CLI/Web
    participant D as Daemon
    participant S as PendingStore
    participant P as Policy
    participant X as PlanExecutor

    O->>C: confirmar pending
    C->>D: confirm(id, respuesta)
    D->>S: load(id)
    S-->>D: propuesta
    D->>P: re-evaluate(plan)
    P-->>D: fresh decision
    alt expirado o D
      D-->>C: rechazado
    else palabra incorrecta
      D-->>C: no confirmado
    else válido
      D->>S: resolve atomic
      D->>X: run(plan)
      X-->>D: resultado + outputs
      D-->>C: resultado
    end
```

## 11. Comunicación

```mermaid
flowchart LR
    PRODUCER[CLI / Web / Routine / Intake] -- Plan --> DISPATCH[dispatch]
    DISPATCH -- evaluate --> POLICY[Policy]
    DISPATCH -- save --> PENDING[PendingStore]
    DISPATCH -- authorized plan --> RUNNER[PlanRunner]
    RUNNER -- Action --> TOOL[Tool adapter]
    TOOL -- ToolResult --> RUNNER
    RUNNER -- terminal result --> AUDIT[Audit]
```

## 12. Visión general de interacción

```mermaid
flowchart TD
    I1[[Productor: owner ask]] --> CORE[[Loop común de política]]
    I2[[Productor: rutina]] --> CORE
    I3[[Productor: intake]] --> CORE
    I4[[Productor: memoria remember]] --> CORE
    CORE --> C{resultado}
    C --> I5[[Ejecución A]]
    C --> I6[[Bandeja B/C]]
    C --> I7[[Rechazo D]]
    I6 --> I8[[Confirmación + re-evaluación]]
    I8 --> I5
```

## 13. Temporal: TTL y cambio de riesgo

```mermaid
sequenceDiagram
    participant T as Tiempo
    participant S as PendingStore
    participant O as Owner
    participant P as Policy

    T->>S: t0 guardar riesgo B, expiresAt
    Note over S: estado pending
    T->>S: t1 cambia filesystem/reglas
    O->>S: t2 confirmar
    S->>P: re-evaluar
    P-->>S: riesgo C
    S-->>O: exigir CONFIRMAR
    T->>S: t3 supera expiresAt
    O->>S: confirmar tarde
    S-->>O: propuesta expirada
```

## 14. Despliegue

```mermaid
flowchart TB
    subgraph PC[PC del owner]
      DAEMON[Wyss daemon]
      CLI[CLI]
      WEB[Web bridge HTTPS]
      DBS[(SQLite DBs)]
      DATA[Archivos/Repos]
      OLLAMA[Ollama opcional]
      LITELLM[LiteLLM opcional]
    end

    PHONE[Browser/PWA/APK] -->|LAN HTTPS| WEB
    CLI -->|Unix socket| DAEMON
    WEB -->|Unix socket| DAEMON
    DAEMON --> DBS
    DAEMON --> DATA
    DAEMON --> OLLAMA
    DAEMON --> LITELLM
    LITELLM --> PROVIDERS[Providers externos]
    DAEMON --> NOTION[Notion API]
    N8N[n8n] -->|bearer intake| WEB
```

## 15. Perfil UML de seguridad

```mermaid
classDiagram
    class CognitivePolicyEngine {
      <<deterministic-authority>>
      <<fail-closed>>
    }
    class LLMOrchestrator {
      <<proposal-only>>
      <<untrusted-output>>
    }
    class PlanExecutor {
      <<authorized-actions-only>>
    }
    class FileSystemAdapter {
      <<second-wall>>
    }
    class PendingStore {
      <<atomic-resolution>>
      <<ttl-enforced>>
    }
    class AuditLogger {
      <<durable-evidence>>
    }
```

## Regla de mantenimiento

Yo actualizo estas vistas cuando cambia un actor, nivel, action type, handler, DB, provider, dispositivo o ruta de ejecución. Un cambio que crea un nuevo productor de planes debe aparecer explícitamente en los diagramas de componentes e interacción.