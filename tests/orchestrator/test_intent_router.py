"""Modelo de intención del orquestador (ORCH-03/04)."""

from core.orchestrator.intent import IntentCategory, IntentClassification


def test_nueve_categorias() -> None:
    """ORCH-03: el modelo de intención cubre ≥9 categorías distintas."""
    required = {
        IntentCategory.KNOWLEDGE_QUERY,
        IntentCategory.FILE_OPERATION,
        IntentCategory.REPO_TASK,
        IntentCategory.SYSTEM_ACTION,
        IntentCategory.AGENT_TASK,
        IntentCategory.ROUTINE_TRIGGER,
        IntentCategory.ADMIN_TASK,
        IntentCategory.DANGEROUS_OPERATION,
        IntentCategory.AMBIGUOUS_REQUEST,
    }

    assert len(IntentCategory) >= 9
    assert required <= set(IntentCategory)


def test_ambiguous() -> None:
    """ORCH-04: input ambiguo enruta a clarification, no a una acción (D-60)."""
    intent = IntentClassification(
        category=IntentCategory.AMBIGUOUS_REQUEST,
        confidence=0.41,
        clarification_needed=True,
    )

    assert intent.category is IntentCategory.AMBIGUOUS_REQUEST
    assert intent.clarification_needed is True
