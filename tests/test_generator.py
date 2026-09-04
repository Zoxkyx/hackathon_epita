from unittest.mock import patch

from src.agents.generator import generate_content


def test_generate_content_first_pass_no_revision_notes():
    fake_result = {"lesson": "texte", "exercises": [{"question": "q", "expected_answer": "a", "concept": "c"}]}
    session_spec = {"title": "Intro", "focus": "bases", "goal": "comprendre X"}
    with patch("src.agents.generator.call_structured", return_value=fake_result) as mock_call:
        result = generate_content(session_spec, "Aucun historique.", None)
    assert result == fake_result
    args, kwargs = mock_call.call_args
    assert "Intro" in args[1]
    assert "Notes de révision" not in args[1]


def test_generate_content_includes_revision_notes():
    fake_result = {"lesson": "texte v2", "exercises": []}
    session_spec = {"title": "Intro", "focus": "bases", "goal": "comprendre X"}
    with patch("src.agents.generator.call_structured", return_value=fake_result) as mock_call:
        generate_content(session_spec, "resume", "simplifier l'exemple 2")
    args, kwargs = mock_call.call_args
    assert "simplifier l'exemple 2" in args[1]
