"""Jerarquía de excepciones del dominio."""


class WyssError(Exception):
    """Raíz de todos los errores del sistema."""


class PolicyViolation(WyssError):
    """La política rechazó un plan (nivel D / outcome REJECT). La raisea AgentBase."""


class AuditIntegrityError(WyssError):
    """El log de auditoría no pudo garantizar durabilidad/integridad (ej. WAL falla)."""
