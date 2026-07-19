# ADR-004 — Yo separo Wyss y Home Edge con servicios de sistema

## Estado

Aceptada.

## Contexto

Yo necesito que `SO_PEERCRED` distinga al owner de Home Edge. Un servicio systemd de usuario no puede cambiar a otro UID y el manager de usuario conserva los grupos de la sesión con la que arrancó.

## Decisión

Yo ejecuto Wyss como `saintwyss` y Home Edge como `wyss-edge` mediante unidades de sistema. Yo comparto únicamente el grupo `wyss-home` y `/run/wyss-home` en modo `0750`; el socket Home queda `0660` y el socket owner continúa `0600`. Los repositorios siguen siendo del owner y los secretos quedan fuera de Git.

## Consecuencias

Yo obtengo aislamiento verificable por UID sin abrir puertos. La instalación requiere privilegios administrativos y un rollback coordinado de dos unidades. Yo no uso este mecanismo para cambiar OAuth, NVS, eFuses ni credenciales de proveedores.
