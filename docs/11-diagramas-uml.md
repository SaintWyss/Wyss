# Wyss — Diagramas UML

**Versión:** 0.1

---

## 1. Diagrama de casos de uso

```plantuml
@startuml
left to right direction
actor Owner
actor Trabajador
actor "Modelo IA externo" as AI
actor "Entorno (SO/Apps)" as OS

rectangle "Wyss" {
  usecase "Dar instrucción" as UC1
  usecase "Consultar conocimiento" as UC2
  usecase "Delegar tarea a agente" as UC3
  usecase "Crear agente" as UC4
  usecase "Habilitar BC" as UC5
  usecase "Ejecutar rutina programada" as UC6
  usecase "Confirmar acción" as UC7
  usecase "Rechazar acción inválida" as UC8
  usecase "Reportar avance" as UC9
  usecase "Auditar" as UC10
  usecase "Ingestar fuente" as UC11
}

Owner --> UC1
Owner --> UC2
Owner --> UC4
Owner --> UC5
Owner --> UC7
Owner --> UC11
UC1 --> UC3
UC3 --> UC8
UC6 --> UC3
Trabajador --> UC9
UC3 --> AI
UC3 --> OS
UC3 ..> UC10 : include
UC8 ..> UC10 : include
UC5 ..> UC10 : include
@enduml
```

## 2. Diagrama de secuencia — delegación con confirmación

```plantuml
@startuml
actor Owner
participant Orquestador as Orq
participant "Policy Engine" as Policy
participant "Agente (dominio)" as Agente
participant "Retrieval Engine" as RAG
participant "Model Gateway" as GW
participant Ejecutor
participant Auditoría

Owner -> Orq: "Organizá el material del parcial"
Orq -> Orq: clasificar intención + dominio
Orq -> Agente: asignar tarea
Agente -> RAG: consultar BC habilitada
RAG --> Agente: material relevante
Agente -> GW: plan asistido (contexto mínimo)
GW --> Agente: propuesta de plan
Agente --> Orq: plan
Orq -> Policy: evaluar(plan)
Policy --> Orq: nivel B (confirmación simple)
Orq -> Owner: mostrar plan
Owner --> Orq: confirmado
Orq -> Agente: ejecutar
Agente -> Ejecutor: acciones
Ejecutor --> Agente: resultado + verificación
Agente --> Orq: reporte
Orq -> Auditoría: log completo
Orq --> Owner: resultado final
@enduml
```

## 3. Diagrama de secuencia — rechazo absoluto

```plantuml
@startuml
actor Solicitante
participant Orquestador as Orq
participant "Policy Engine" as Policy
participant Auditoría

Solicitante -> Orq: "Borrá la BC completa sin backup"
Orq -> Policy: evaluar(plan destructivo)
Policy --> Orq: nivel D → reject(razón)
Orq -> Auditoría: registrar intento
Orq --> Solicitante: rechazo explicado + alternativa segura
@enduml
```

## 4. Diagrama de estados de una tarea

```plantuml
@startuml
[*] --> Recibida
Recibida --> Clasificada
Clasificada --> Delegada : dominio identificado
Clasificada --> Aclaración : ambigua
Aclaración --> Clasificada
Delegada --> Planificada
Planificada --> Evaluada
Evaluada --> Rechazada : nivel D
Evaluada --> EsperandoConfirmación : nivel B/C
Evaluada --> Ejecutando : nivel A
EsperandoConfirmación --> Cancelada : owner no confirma
EsperandoConfirmación --> Ejecutando : confirmada
Ejecutando --> Verificando
Verificando --> Completada
Verificando --> Fallida
Rechazada --> [*]
Cancelada --> [*]
Completada --> [*]
Fallida --> [*]
@enduml
```

## 5. Diagrama de actividad — flujo general

```plantuml
@startuml
start
:Owner da instrucción;
:Clasificar intención;
if (¿Ambigua?) then (sí)
  :Pedir aclaración;
  stop
endif
if (¿Consulta de conocimiento?) then (sí)
  :Retrieval Engine resuelve;
  :Responder;
  stop
endif
:Identificar dominio y delegar a agente;
:Agente genera plan;
:Policy Engine evalúa;
if (¿Nivel D?) then (sí)
  :Rechazar + explicar + auditar;
  stop
endif
if (¿Requiere confirmación?) then (sí)
  :Mostrar plan al owner;
  if (¿Confirma?) then (no)
    :Cancelar + auditar;
    stop
  endif
endif
:Ejecutar acciones;
:Verificar resultado;
:Reportar al orquestador;
:Auditar;
:Responder al owner;
stop
@enduml
```

## 6. Diagrama de despliegue v0.1

```plantuml
@startuml
node "PC del Owner" {
  artifact "Interfaz CLI/chat"
  component "Núcleo Wyss (daemon)"
  component "Agent Runtime"
  database "SQLite (datos + FTS5)"
  database "Índice vectorial local"
  component "Adaptadores"
  folder "Bases de Conocimiento (archivos)"
}

cloud "Proveedores IA" {
  component "Modelos fuertes"
  component "Modelos económicos"
}

component "Model Gateway"

"Interfaz CLI/chat" --> "Núcleo Wyss (daemon)"
"Núcleo Wyss (daemon)" --> "SQLite (datos + FTS5)"
"Núcleo Wyss (daemon)" --> "Agent Runtime"
"Agent Runtime" --> "Adaptadores"
"Agent Runtime" --> "Índice vectorial local"
"Adaptadores" --> "Bases de Conocimiento (archivos)"
"Agent Runtime" --> "Model Gateway"
"Model Gateway" --> "Modelos fuertes"
"Model Gateway" --> "Modelos económicos"
@enduml
```

## 7. Diagrama de clases preliminar

```plantuml
@startuml
class WyssCore {
  +handle(command): TaskResult
}
class Orchestrator {
  +route(task): Agent
  +consolidate(reports): Result
}
class IntentRouter {
  +classify(command): Intent
}
class TaskPlanner {
  +createPlan(intent, context): Plan
}
class CognitivePolicyEngine {
  +evaluate(plan): PolicyDecision
}
class PermissionManager {
  +grant(subject, kb): Permission
  +check(subject, kb): bool
  +revoke(permission): void
}
class AgentBase {
  +receive(task): Plan
  +execute(plan): Report
  #queryKnowledge(query): Results
}
class RetrievalEngine {
  +search(query, allowedKBs): Results
}
class ModelGateway {
  +route(request): ModelResponse
  -minimizeContext(ctx): ctx
}
class RoutineScheduler {
  +tick(): void
}
class ConfirmationManager {
  +request(decision): Confirmation
}
class AuditLogger {
  +log(event): void
}

WyssCore --> IntentRouter
WyssCore --> Orchestrator
Orchestrator --> TaskPlanner
Orchestrator --> CognitivePolicyEngine
Orchestrator --> ConfirmationManager
Orchestrator --> "1..*" AgentBase
Orchestrator --> AuditLogger
RoutineScheduler --> Orchestrator
AgentBase --> RetrievalEngine
AgentBase --> ModelGateway
RetrievalEngine --> PermissionManager
AgentBase --> AuditLogger
@enduml
```
