"""Contrato de presentación segura de planes Home."""

from core.domain.plan import Action
from orchestrator.home_plan_preview import home_action_step


def test_home_step_includes_material_parameters() -> None:
    step = home_action_step(
        Action(
            "file.move",
            "/tmp/source.txt",
            {"destination": "/tmp/final.txt", "overwrite": False},
        )
    )

    assert step == {
        "description": "file.move",
        "target": "/tmp/source.txt",
        "parameters": {"destination": "/tmp/final.txt", "overwrite": False},
    }


def test_home_step_redacts_sensitive_parameter_names() -> None:
    step = home_action_step(
        Action("provider.call", "calendar", {"oauth_token": "no-debe-salir", "calendar": "Casa"})
    )

    assert step["parameters"] == {
        "calendar": "Casa",
        "oauth_token": {"redacted": True},
    }
    assert "no-debe-salir" not in str(step)


def test_home_step_bounds_long_content_with_verifiable_digest() -> None:
    content = "x" * 300
    step = home_action_step(Action("file.write", "/tmp/a", {"content": content}))

    preview = step["parameters"]
    assert isinstance(preview, dict)
    bounded = preview["content"]
    assert isinstance(bounded, dict)
    assert bounded["preview"] == "x" * 256
    assert bounded["characters"] == 300
    assert bounded["truncated"] is True
    assert len(str(bounded["sha256"])) == 64
