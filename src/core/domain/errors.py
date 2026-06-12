"""Jerarquía de excepciones del dominio."""


class WyssError(Exception):
    """Raíz de todos los errores del sistema."""


class PolicyViolation(WyssError):
    """La política rechazó un plan (nivel D / outcome REJECT). La raisea AgentBase."""


class AuditIntegrityError(WyssError):
    """El log de auditoría no pudo garantizar durabilidad/integridad (ej. WAL falla)."""


class TraceIntegrityError(WyssError):
    """El store de traces no pudo garantizar durabilidad (ej. WAL falla sobre NTFS).

    Análogo a `AuditIntegrityError` pero para `traces.db` (DB separada, D-22). Lo levanta
    `TraceStore` al construir si `PRAGMA journal_mode` no retorna ``"wal"`` (Pitfall 6).
    """


class ConfigError(WyssError):
    """La configuración de boot no pudo cargarse/validarse (fail-fast con mensaje legible).

    La levanta el bootstrap ante un config inexistente, un TOML mal formado o un modelo
    Pydantic inválido (typo, tipo malo, clave extra). El mensaje nombra el path y, para
    errores de validación, el campo (loc) — el caller CLI (Fase 5) decide el `sys.exit`.
    """


class SecretDetected(WyssError):
    """Payload bloqueado: matcheó un patrón de secreto. La llamada NO sale (fail-closed, D-20).

    NUNCA recibe ni loguea el valor del secreto: el constructor solo toma el NOMBRE del
    patrón que matcheó. Así el rastro de auditoría (V7) registra el motivo sin filtrar la clave.
    """

    def __init__(self, pattern_name: str) -> None:
        super().__init__(f"payload bloqueado: matcheó patrón de secreto '{pattern_name}'")
        self.pattern_name = pattern_name  # nombre del patrón, JAMÁS el secreto


class BudgetExceeded(WyssError):
    """Presupuesto (global o por-agente) agotado: la llamada se veta pre-autorización (D-18).

    El gate de costo la levanta ANTES de llamar al provider, no después — el presupuesto
    es enforced, no advisory (Pitfall 2).
    """


class UnknownTier(WyssError):
    """El tier pedido no existe en la config del router: error explícito, sin fallback (D-17).

    Expone `tier` (el pedido) y `available` (los tiers configurados) para que el caller y la
    auditoría puedan reportar con claridad. Nunca enruta silenciosamente a un default.
    """

    def __init__(self, tier: str, *, available: tuple[str, ...]) -> None:
        super().__init__(
            f"tier desconocido '{tier}'; tiers disponibles: {', '.join(available) or '(ninguno)'}"
        )
        self.tier = tier
        self.available = available
