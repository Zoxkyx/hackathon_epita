from unittest.mock import patch

from src.agents.diagnostician import diagnose


def test_diagnose_passes_exercises_and_reactions_returns_health_report():
    reactions = {"e1": {"answers": [{"question": "q", "given_answer": "faux"}], "reaction_text": "perdu"}}
    exercises = [{"question": "q", "expected_answer": "vrai", "concept": "boucle for"}]
    fake_result = {
        "collective_confusion": ["boucle for"],
        "boredom_level": 0.2,
        "dropout_risk_students": ["e1"],
        "fragile_concepts": ["boucle for"],
        "needs_revision": True,
        "summary": "e1 est perdu sur les boucles",
        "success_rate_by_concept": {"boucle for": 0.0},
        "graded_answers": [{"student_id": "e1", "question": "q", "correct": False}],
    }
    with patch("src.agents.diagnostician.call_structured", return_value=fake_result) as mock_call:
        result = diagnose(reactions, exercises)
    assert result == fake_result
    _, user_arg = mock_call.call_args[0][:2]
    assert "e1" in user_arg
    assert "vrai" in user_arg
