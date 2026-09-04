from unittest.mock import patch

from src.agents.reviser import revise_instructions


def test_revise_instructions_returns_notes_string():
    diagnosis = {"summary": "e1 est perdu", "needs_revision": True}
    content = {"lesson": "texte", "exercises": []}
    fake_result = {"revision_notes": "simplifier l'exemple 2"}
    with patch("src.agents.reviser.call_structured", return_value=fake_result) as mock_call:
        result = revise_instructions(diagnosis, content)
    assert result == "simplifier l'exemple 2"
    assert "e1 est perdu" in mock_call.call_args[0][1]
