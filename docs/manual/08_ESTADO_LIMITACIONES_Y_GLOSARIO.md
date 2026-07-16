# 08 — Estado, limitaciones, roadmap y glosario

## Estado actual

| Capacidad | Estado |
|---|---|
| política A–D y denylist | implementada y probada |
| daemon JSON-RPC | implementado |
| ejecución archivos/shell/Git | implementada con límites |
| confirmación y re-evaluación | implementadas |
| auditoría CLI | implementada |
| RPC audit | stub |
| undo | implementado para `file.*` compatibles |
| ingesta y búsqueda híbrida | implementadas |
| gateway/costos/minimización | implementados |
| modo deterministic | implementado |
| modo LLM | implementado y validado con Qwen/LiteLLM local |
| Pellegrini/ledger | implementado en el estado actual del repo |
| rutinas | implementadas |
| memoria | implementada |
| digest | implementado |
| Notion | implementado; requiere token y recursos reales |
| intake n8n | implementado y opt-in |
| web/PWA | implementada y smoke físico aprobado |
| APK Android | implementado y validado en teléfono real |
| release formal v1 | pendiente de versionado/artefactos unificados |

## Limitaciones conocidas

- single-owner y enfoque local;
- Unix socket orientado a Linux;
- SQLite requiere WAL y filesystem compatible;
- permisos `chmod` no confiables en NTFS;
- undo no cubre shell/Git/Notion en general;
- RPC audit vacío;
- certificados self-signed generan fricción y limitan service worker;
- primer trust de APK depende de un pairing confiable;
- CI raíz no valida toda la matriz web/Android;
- providers y Notion dependen de servicios externos;
- rutinas almacenan planes serializados y requieren compatibilidad de schema;
- no existe equipo multiusuario completo;
- extracción de agentes/SDK está en evolución.

## Roadmap recomendado

### 1. Release y empaquetado

- unificar versión de package, docs, web y APK;
- publicar changelog v1;
- generar artefactos con checksums/SBOM;
- firma de APK/binarios;
- instalador y systemd soportados.

### 2. Observabilidad y operación

- implementar RPC audit;
- métricas del daemon;
- dashboard de costos/rutinas;
- backups consistentes;
- restore drills;
- health más expresivo.

### 3. Seguridad

- gestión de secretos del host;
- mayor cobertura de actions;
- undo ampliado donde sea reversible;
- hardening de pairing inicial;
- rate limits persistentes;
- auditoría de dependencias y releases.

### 4. Arquitectura de agentes

- consolidar `wyss-core`/SDK;
- conectar agentes externos por contratos estables;
- versionar capacidades;
- mantener un único dispatch;
- evitar dependencias circulares entre repos.

### 5. Producto

- UX de configuración;
- actualización automática controlada;
- mejor soporte Wayland/otras plataformas;
- modo equipo solo con modelo de identidad, tenancy y permisos completo.

## Glosario

**Owner:** persona con autoridad final sobre Wyss.

**Orquestador:** componente que interpreta una instrucción y propone un plan.

**LLM:** modelo de lenguaje; en Wyss propone, no decide riesgo.

**Plan:** conjunto tipado de acciones con resumen y justificación.

**Action:** operación concreta como leer, mover o ejecutar.

**PolicyDecision:** resultado determinista con nivel y outcome.

**Nivel A:** lectura o diagnóstico ejecutable directamente.

**Nivel B:** modificación normal con confirmación simple.

**Nivel C:** alto impacto con confirmación fuerte.

**Nivel D:** acción prohibida y no confirmable.

**Denylist:** reglas de rechazo absoluto.

**Segunda muralla:** validaciones dentro de cada adapter antes del efecto real.

**Pending:** propuesta B/C almacenada hasta confirmar, rechazar o expirar.

**TTL:** tiempo máximo de validez.

**Re-evaluación:** nueva evaluación de política al confirmar.

**Daemon:** proceso persistente que atiende JSON-RPC.

**Unix socket:** canal local entre procesos sin puerto de red.

**Composition root:** lugar donde yo construyo e inyecto implementaciones.

**Port:** contrato del core.

**Adapter:** implementación concreta de un port.

**Gateway:** única salida controlada hacia modelos.

**Tier:** categoría de modelo/costo configurada.

**Context minimizer:** componente que reduce y sanitiza lo enviado al provider.

**RRF:** Reciprocal Rank Fusion, método para combinar rankings FTS y vectorial.

**FTS5:** búsqueda de texto completo de SQLite.

**Embedding:** vector que representa significado aproximado.

**Trust tier:** nivel de confianza de un hecho de memoria.

**Intake:** propuesta recibida desde una automatización externa.

**TOFU:** Trust On First Use; confiar la primera huella y detectar cambios.

**Pinning:** asociar la app a una huella de certificado esperada.

**WAL:** Write-Ahead Log de SQLite.

**Undo journal:** registro de efectos e información necesaria para invertirlos.

**Fail-closed:** rechazar ante incertidumbre.

**Smoke físico:** verificación en hardware/dispositivo real.

## Cierre

Yo considero Wyss funcional en un alcance amplio de uso personal, pero mantengo una diferencia clara entre alcance implementado y release formalmente empaquetada. La seguridad depende de conservar la jerarquía owner → policy → tools y de no convertir conveniencia en bypass.