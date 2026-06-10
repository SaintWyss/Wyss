# Wyss — Definición de Hecho (Definition of Done)

**Versión:** 0.1

---

Una funcionalidad de Wyss se considera **terminada** únicamente cuando cumple todos estos puntos:

## 1. Diseño
- [ ] Tiene caso de uso documentado (o referencia a uno existente).
- [ ] Tiene su nivel de riesgo definido (A–D) y política asociada.
- [ ] Está reflejada en los diagramas correspondientes si cambia la arquitectura.

## 2. Comportamiento
- [ ] Tiene flujo feliz documentado y probado.
- [ ] Tiene flujos alternativos y de error definidos y manejados.
- [ ] Si modifica estado: pide confirmación según su nivel.
- [ ] Si es de nivel D: el rechazo está probado explícitamente.
- [ ] Verifica su resultado después de ejecutar.

## 3. Seguridad
- [ ] Respeta las habilitaciones (probado con acceso no autorizado → bloqueado).
- [ ] No expone secretos ni los envía a modelos externos.
- [ ] No abre ninguna vía de dirección horizontal entre agentes.
- [ ] No permite auto-modificación de permisos o políticas.

## 4. Observabilidad
- [ ] Registra auditoría completa (actor, plan, decisión, resultado).
- [ ] Registra costos si usa modelos externos.
- [ ] Sus errores son diagnosticables desde los logs.

## 5. Calidad
- [ ] Tiene pruebas mínimas automatizadas.
- [ ] Maneja errores sin dejar el entorno inconsistente.
- [ ] Si es reversible por naturaleza: tiene rollback o backup.

## 6. Documentación
- [ ] Documentación de usuario (cómo la usa el owner).
- [ ] Documentación técnica (cómo funciona, decisiones tomadas).
- [ ] El glosario está actualizado si introduce términos nuevos.

---

## Regla final

> Si una funcionalidad rompe un límite de la seguridad cognitiva o de la jerarquía owner → orquestador → agentes, **no está hecha, está rota** — sin importar cuán bien funcione.
