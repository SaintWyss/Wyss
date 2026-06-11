"""Puerto de persistencia de permisos — la lógica de reglas vive en core, no acá."""

from collections.abc import Sequence
from typing import Protocol

from core.domain import Permission, Subject


class PermissionStore(Protocol):
    """Persiste y consulta habilitaciones; la decisión de acceso la toma el core."""

    def grants_for(self, subject: Subject) -> Sequence[Permission]: ...

    def save(self, permission: Permission) -> None: ...

    def revoke(self, permission_id: str) -> None: ...
