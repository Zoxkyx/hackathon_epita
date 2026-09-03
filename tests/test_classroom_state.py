from src.memory.classroom_state import ClassroomState, StudentMemory


def test_student_memory_roundtrip():
    mem = StudentMemory(profile="rapide", mastered_concepts=["a"])
    mem2 = StudentMemory.from_dict(mem.to_dict())
    assert mem2.profile == "rapide"
    assert mem2.mastered_concepts == ["a"]


def test_new_from_personas():
    personas = [
        {"id": "e1", "profile": "rapide", "misconceptions": []},
        {"id": "e2", "profile": "lent", "misconceptions": ["confond a et b"]},
    ]
    state = ClassroomState.new_from_personas(personas)
    assert set(state.students.keys()) == {"e1", "e2"}
    assert state.students["e1"].mastered_concepts == []


def test_update_student():
    state = ClassroomState.new_from_personas([{"id": "e1", "profile": "rapide", "misconceptions": []}])
    state.update_student("e1", {
        "profile": "rapide", "mastered_concepts": ["boucles"], "shaky_concepts": [],
        "forgotten_concepts": [], "engagement_trend": [0.8], "history_notes": "a bien suivi",
    })
    assert state.students["e1"].mastered_concepts == ["boucles"]


def test_save_and_load(tmp_path):
    state = ClassroomState.new_from_personas([{"id": "e1", "profile": "rapide", "misconceptions": []}])
    path = tmp_path / "state.json"
    state.save(str(path))
    loaded = ClassroomState.load(str(path))
    assert loaded.students["e1"].profile == "rapide"
