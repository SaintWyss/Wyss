"""Memoria operativa de agentes con write-path restringido (D-71).

La memoria persiste markdown por agente y se lee libremente para construir contexto.
El único camino de escritura es ``write_supervised``: debe usarse solo desde el owner
o desde extracción supervisada. Contenido recuperado de BC no debe llegar a este
método, ni debe llamarse desde el ciclo ``_run``.
"""

from pathlib import Path


class AgentMemory:
    """Carga y persiste ``MEMORY.md`` para un agente."""

    _TEMPLATE = """# Memoria del Agente {agent_id}

## Preferencias del owner

- Sin preferencias registradas.

## Patrones del dominio

- Sin patrones registrados.

## Notas de sesiones anteriores

- Sin notas registradas.
"""

    def __init__(self, agent_id: str, data_dir: Path) -> None:
        self._agent_id = agent_id
        self._path = data_dir / "agents" / agent_id / "MEMORY.md"

    def load(self) -> str:
        """Retorna la memoria existente o una plantilla sin crear archivos."""
        if not self._path.exists():
            return self._TEMPLATE.format(agent_id=self._agent_id)
        return self._path.read_text(encoding="utf-8")

    def write_supervised(self, content: str) -> None:
        """Escribe memoria solo por flujo supervisado D-71.

        Este método es el único write-path: owner/extracción supervisada pueden
        invocarlo, pero contenido de BC jamás debe conectarse acá ni llamarse desde
        el ciclo ``_run`` del agente.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content, encoding="utf-8")
