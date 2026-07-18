# ADR-003 — Yo separo la capacidad RPC de Home Edge

**Estado:** aceptada
**Fecha:** 2026-07-18

## Contexto

Yo necesito que Home Edge invoque la autoridad pública de Wyss sin recibir, por transitividad,
acceso a auditoría con payload, memoria, rutinas ni operaciones administrativas. Un único socket
Unix `0600` autentica al usuario del sistema, pero no limita los métodos que puede invocar el
proceso Edge.

## Decisión

Yo mantengo `wyss.sock` `0600` dentro del data dir privado como límite owner/administrativo y creo
`wyss-home.sock` `0660` en un runtime dir separado `0750`, preparado para un grupo compartido entre
Wyss y una cuenta de sistema Edge. En el socket Home verifico el
UID real del peer con `SO_PEERCRED`, aplico una allowlist cerrada (`home.intent`,
`home.plan.answer` y `status`), derivo la identidad de autoridad como `home-edge` en el transporte y
no confío en el campo `source` recibido. El socket Home sólo arranca si existen un UID Edge
distinto, un grupo compartido, un runtime dir precreado con permisos exactos, un executor real y un
store idempotente durable; el mismo UID del owner se rechaza.

Yo limito tasa y profundidad antes de ejecutar handlers. Las confirmaciones usan una revisión
persistida y un compare-and-swap que incluye estado, TTL y revisión dentro de la misma transacción.
Cada transición terminal incrementa la revisión. Los claims idempotentes tienen permisos `0600`,
cuota y mantenimiento acotado; yo nunca podo automáticamente un claim `in_progress` ambiguo.

## Consecuencias

- Yo impido por DAC que el UID de Edge abra el socket owner y verifico su UID en el socket Home.
- Yo fallo cerrado si faltan ejecución verificable, idempotencia o capacidad de almacenamiento.
- Yo puedo revocar el acceso de Edge retirando sólo el socket dedicado sin detener la CLI owner.
- Yo delego la identidad de cada panel o teléfono al futuro handshake autenticado Protocol v2;
  este límite sólo autentica al proceso Home Edge local.

## Alternativas descartadas

- Yo descarto compartir el socket owner porque amplía la capacidad del Edge innecesariamente.
- Yo descarto confiar en `source` porque es texto controlado por el caller.
- Yo descarto confirmar fuera de la transacción porque reabre carreras con TTL y otros clientes.

## Rollback

Yo puedo detener Home Edge y retirar `wyss-home.sock` sin alterar `wyss.sock` ni las bases. No
retrocedo a un socket compartido; si la migración falla, Home queda degradado y el owner conserva
la operación local.
