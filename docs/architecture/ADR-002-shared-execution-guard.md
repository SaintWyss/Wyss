# ADR-002 — Yo aplico una segunda muralla común antes del I/O

**Estado:** aceptada  
**Fecha:** 2026-07-18

## Contexto

Yo tenía una re-evaluación determinista de política en el adapter de filesystem, pero Shell y Git
dependían sólo de sus allowlists. Una allowlist reduce superficie, pero no reemplaza la política:
una acción que ahora clasifica D debe quedar rechazada aunque el binario o subcomando esté permitido.

## Decisión

Yo defino `ExecutionGuardPort` en `core` y cableo una única instancia de
`DeterministicExecutionGuard` desde el composition root. Cada adapter vuelve a evaluar la acción
efectiva después de normalizar y validar sus argumentos, inmediatamente antes de crear el proceso o
realizar el I/O. El guard bloquea en modo fail-closed cualquier `REJECT` y cualquier riesgo superior
al techo declarado por el adapter, y registra el bloqueo sin incluir parámetros potencialmente
secretos.

Yo mantengo la resolución y protección de symlinks dentro de filesystem porque son restricciones
propias de ese adapter. Shell y Git conservan sus allowlists y ejecutan siempre con argv, nunca con
un shell intermediario. `shell.run`, `git.commit` y `git.push` tienen techo C: pueden ejecutarse sólo
después del gate fuerte anterior, mientras que D nunca atraviesa esta segunda muralla.

## Consecuencias

- Yo tengo una sola semántica de re-evaluación para los adapters con I/O real.
- Yo puedo probar que una entrada allowlisted de nivel D no crea ningún proceso.
- Yo mantengo la política determinista separada del transporte y de los detalles del adapter.
- Yo debo inyectar el guard en todo adapter nuevo que produzca efectos externos.

## Alternativas descartadas

- Yo descarto usar sólo allowlists porque no expresan reglas contextuales A–D.
- Yo descarto duplicar la evaluación en cada adapter porque las reglas podrían divergir.
- Yo descarto considerar todo Shell/Git nivel B porque commit, push y shell son operaciones C.

## Rollback

Yo puedo revertir el cableado y este puerto como una unidad. No habilito un modo operativo sin
segunda muralla: ante una falla de inicialización, el composition root debe fallar cerrado.
