from unittest.mock import patch

from src.agents.student import react_to_content
from src.memory.classroom_state import StudentMemory


def test_react_to_content_returns_structured_reaction_and_hides_expected_answer():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": ["confond a et b"]}
    memory = StudentMemory(profile="rapide", mastered_concepts=["variables"])
    content = {"lesson": "les boucles for", "exercises": [{"question": "q1", "expected_answer": "SECRET", "concept": "boucle for"}]}
    fake_result = {
        "answers": [{"question": "q1", "given_answer": "ma réponse"}],
        "reaction_text": "facile",
        "updated_memory": {
            "profile": "rapide", "mastered_concepts": ["variables", "boucle for"],
            "shaky_concepts": [], "forgotten_concepts": [], "engagement_trend": [0.9],
            "history_notes": "a bien suivi",
        },
    }
    with patch("src.agents.student.call_structured", return_value=fake_result) as mock_call:
        result = react_to_content("e1", persona, memory, content)
    assert result == fake_result
    system_arg, user_arg = mock_call.call_args[0][:2]
    assert "confond a et b" in system_arg
    assert "les boucles for" not in user_arg or "q1" in user_arg
    assert "SECRET" not in user_arg
    assert mock_call.call_args.kwargs.get("cacheable_system") is True


def test_react_to_content_includes_violation_notes_when_retrying():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": []}
    memory = StudentMemory(profile="rapide")
    content = {"lesson": "l", "exercises": [{"question": "q1", "expected_answer": "a", "concept": "c"}]}
    fake_result = {"answers": [], "reaction_text": "x", "updated_memory": {
        "profile": "rapide", "mastered_concepts": [], "shaky_concepts": [],
        "forgotten_concepts": [], "engagement_trend": [], "history_notes": "",
    }}
    with patch("src.agents.student.call_structured", return_value=fake_result) as mock_call:
        react_to_content("e1", persona, memory, content, violation_notes=["concept jamais enseigné"])
    _, user_arg = mock_call.call_args[0][:2]
    assert "concept jamais enseigné" in user_arg