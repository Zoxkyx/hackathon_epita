from src.fake_agents import (
    fake_diagnose,
    fake_generate_content,
    fake_plan_sessions,
    fake_react_to_content,
    fake_revise_instructions,
)
from src.memory.classroom_state import StudentMemory


def test_fake_plan_sessions_returns_n_sessions():
    sessions = fake_plan_sessions("objectif", 3)
    assert len(sessions) == 3
    for s in sessions:
        assert set(s.keys()) == {"title", "focus", "goal"}


def test_fake_generate_content_has_exercises_with_concept():
    session_spec = {"title": "S1", "focus": "boucles", "goal": "g"}
    content = fake_generate_content(session_spec, "resume", None)
    assert content["exercises"][0]["concept"] == "boucles"
    assert "expected_answer" in content["exercises"][0]


def test_fake_react_to_content_answers_and_masters_current_concept():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": []}
    memory = StudentMemory(profile="rapide")
    content = {"lesson": "l", "exercises": [{"question": "q", "expected_answer": "a", "concept": "boucles"}]}
    reaction = fake_react_to_content("e1", persona, memory, content)
    assert reaction["answers"][0]["question"] == "q"
    assert "boucles" in reaction["updated_memory"]["mastered_concepts"]


def test_fake_diagnose_returns_success_rate_per_concept():
    exercises = [{"question": "q", "expected_answer": "a", "concept": "boucles"}]
    result = fake_diagnose({"e1": {}}, exercises)
    assert result["success_rate_by_concept"]["boucles"] == 1.0
    assert result["needs_revision"] is False


def test_fake_revise_instructions_returns_string():
    assert isinstance(fake_revise_instructions({}, {}), str)
