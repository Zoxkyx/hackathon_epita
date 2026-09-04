from src.agents.drift_watcher import check_drift, clamp_reaction, validate_reaction
from src.memory.classroom_state import StudentMemory


def make_reaction(mastered=None, forgotten=None, engagement=None):
    return {
        "answers": [], "reaction_text": "",
        "updated_memory": {
            "profile": "rapide",
            "mastered_concepts": mastered or [],
            "shaky_concepts": [],
            "forgotten_concepts": forgotten or [],
            "engagement_trend": engagement or [],
            "history_notes": "",
        },
    }


def test_validate_reaction_rejects_mastery_of_untaught_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(mastered=["boucle for"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts=set())
    assert is_valid is False
    assert any("jamais enseigné" in r for r in reasons)


def test_validate_reaction_accepts_mastery_of_taught_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(mastered=["boucle for"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"boucle for"})
    assert is_valid is True
    assert reasons == []


def test_validate_reaction_rejects_forgetting_never_known_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(forgotten=["variables"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"variables"})
    assert is_valid is False
    assert any("n'était pas acquis" in r for r in reasons)


def test_validate_reaction_accepts_forgetting_previously_mastered_concept():
    prev = StudentMemory(profile="rapide", mastered_concepts=["variables"])
    reaction = make_reaction(forgotten=["variables"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"variables"})
    assert is_valid is True


def test_validate_reaction_rejects_large_engagement_jump():
    prev = StudentMemory(profile="rapide", engagement_trend=[0.2])
    reaction = make_reaction(engagement=[0.9])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts=set())
    assert is_valid is False
    assert any("Engagement" in r for r in reasons)


def test_clamp_reaction_removes_illegitimate_mastery_and_clamps_engagement():
    prev = StudentMemory(profile="rapide", engagement_trend=[0.2])
    reaction = make_reaction(mastered=["x", "boucle for"], engagement=[0.9])
    clamped = clamp_reaction(reaction, prev, taught_concepts={"boucle for"})
    assert clamped["updated_memory"]["mastered_concepts"] == ["boucle for"]
    assert clamped["updated_memory"]["engagement_trend"] == [0.6]


def test_check_drift_empty_history():
    assert check_drift([]) == []


def test_check_drift_stagnation():
    d = {"needs_revision": True, "summary": "toujours perdu", "boredom_level": 0.3, "fragile_concepts": ["x"], "collective_confusion": ["x"]}
    flags = check_drift([d, dict(d)])
    assert any("stagnation" in f.lower() for f in flags)


def test_check_drift_perfect_class_flagged():
    d = {"needs_revision": False, "summary": "tout va bien", "boredom_level": 0.0, "fragile_concepts": [], "collective_confusion": []}
    flags = check_drift([d, dict(d)])
    assert len(flags) >= 1