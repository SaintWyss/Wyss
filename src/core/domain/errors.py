"""Jerarquía de excepciones del dominio."""


class WyssError(Exception):
    """Raíz de todos los errores del sistema."""


class PolicyViolation(WyssError):
    """La política rechazó un plan (nivel D / outcome REJECT). La raisea AgentBase."""


class AuditIntegrityError(WyssError):
    """El log de auditoría no pudo garantizar durabilidad/integridad (ej. WAL falla)."""


class ConfigError(WyssError):
    """La configuración de boot no pudo cargarse/validarse (fail-fast con mensaje legible).

    La levanta el bootstrap ante un config inexistente, un TOML mal formado o un modelo
    Pydantic inválido (typo, tipo malo, clave extra). El mensaje nombra el path y, para
    errores de validación, el campo (loc) — el caller CLI (Fase 5) decide el `sys.exit`.
    """
