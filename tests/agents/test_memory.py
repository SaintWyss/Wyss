"""Tests de AgentMemory — memoria operativa por agente (AGENT-08).

Wave 0 — RED: AgentMemory aún no existe; los tests fallan por ImportError.
"""

from __future__ import annotations

from pathlib import Path


def test_load_returns_template_when_missing(tmp_path: Path) -> None:
    """AGENT-08: AgentMemory.load() retorna una plantilla cuando MEMORY.md no existe.

    El agente opera sin error aunque sea la primera vez que se instancia.
    La plantilla debe contener el agent_id para identificar al agente.
    """
    from agents.memory import AgentMemory

    memory = AgentMemory(agent_id="test-agent", data_dir=tmp_path)

    content = memory.load()

    assert isinstance(content, str), "load() debe retornar str"
    assert len(content) > 0, "La plantilla no debe ser vacía"
    # La plantilla debe mencionar al agente (para orientar al LLM)
    assert "test-agent" in content, (
        f"La plantilla debe incluir el agent_id 'test-agent'; contenido: {content!r}"
    )
    # El archivo no debe haberse creado (load es read-only)
    memory_path = tmp_path / "agents" / "test-agent" / "MEMORY.md"
    assert not memory_path.exists(), (
        "load() NO debe crear MEMORY.md — es read-only; write_supervised es el write-path"
    )


def test_write_supervised_creates_file(tmp_path: Path) -> None:
    """AGENT-08: write_supervised() crea MEMORY.md y permite lectura posterior.

    Solo el owner o una extracción supervisada llama write_supervised.
    El contenido de BC jamás escribe memoria directamente (anti-poisoning, D-71).
    """
    from agents.memory import AgentMemory

    memory = AgentMemory(agent_id="test-agent", data_dir=tmp_path)

    content_to_write = "# Memoria del Agente test-agent\n\n- Aprendizaje 1\n"
    memory.write_supervised(content_to_write)

    memory_path = tmp_path / "agents" / "test-agent" / "MEMORY.md"
    assert memory_path.exists(), f"write_supervised() debe crear {memory_path}"
    written = memory_path.read_text(encoding="utf-8")
    assert written == content_to_write, f"El contenido escrito no coincide: {written!r}"

    # Verificar que load() ahora retorna el contenido escrito
    loaded = memory.load()
    assert loaded == content_to_write, (
        "load() después de write_supervised debe retornar el contenido escrito"
    )
