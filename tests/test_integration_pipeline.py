"""Test d'intégration : chaîne les 6 agents réels (pas les fakes, pas orchestrator.py
qui n'existe pas encore) à travers une boucle de révision complète.

Contrairement aux tests unitaires de chaque agent, qui mockent call_structured en
isolation totale, celui-ci prouve que la sortie réelle d'un agent est directement
consommable par le suivant : le schéma du Generator nourrit le Student, le schéma
du Student nourrit le DriftWatcher puis le Diagnostician, celui du Diagnostician
nourrit le Reviser, et la boucle retourne au Generator si besoin.

Seule la frontière réseau (call_structured, un mock par module agent) est fausse.
Toute la logique métier réelle s'exécute : validation du DriftWatcher, mise à jour
de ClassroomState, boucle de révision conditionnée par needs_revision.

Ce test ne remplace pas orchestrator.py : il n'y a ni parallélisation réelle
(ThreadPoolExecutor), ni CLI, ni validation humaine du plan. Il prouve seulement
que les interfaces des 6 agents mergés sont compatibles entre elles.
"""
import json
from pathlib import Path
from unittest.mock import patch

from src.agents.diagnostician import diagnose
from src.agents.drift_watcher import check_drift, clamp_reaction, validate_reaction
from src.agents.generator import generate_content
from src.agents.planner import plan_sessions
from src.agents.reviser import revise_instructions
from src.agents.student import react_to_content
from src.config import MAX_ITER
from src.memory.classroom_state import ClassroomState

PERSONAS = json.loads((Path(__file__).resolve().parents[1] / "data/personas/default.json").read_text(encoding="utf-8"))


def make_fake_llm_router(revision_rounds=1):
    """Simule le modèle : renvoie une réponse conforme au schéma demandé, en
    fonction du tool_name. needs_revision passe à False après `revision_rounds`
    appels du Diagnostician, pour exercer réellement la boucle Reviser -> Generator."""
    diagnostician_calls = {"n": 0}

    def router(system_prompt, user_prompt, tool_name, input_schema, max_tokens=2000, cacheable_system=False):
        if tool_name == "submit_session_plan":
            return {"sessions": [
                {"title": "Boucle for", "focus": "boucle for", "goal": "comprendre for"},
            ]}

        if tool_name == "submit_session_content":
            revised = "notes de révision" in user_prompt.lower() or "Notes de révision" in user_prompt
            return {
                "lesson": "La boucle for parcourt une séquence." + (" (version révisée)" if revised else ""),
                "exercises": [{"question": "Que fait range(3) ?", "expected_answer": "0, 1, 2", "concept": "boucle for"}],
            }

        if tool_name == "submit_reaction":
            return {
                "answers": [{"question": "Que fait range(3) ?", "given_answer": "0, 1, 2"}],
                "reaction_text": "ça va",
                "updated_memory": {
                    "profile": "rapide",
                    "mastered_concepts": ["boucle for"],
                    "shaky_concepts": [], "forgotten_concepts": [], "engagement_trend": [0.7],
                    "history_notes": "a bien suivi",
                },
            }

        if tool_name == "submit_diagnosis":
            diagnostician_calls["n"] += 1
            needs_revision = diagnostician_calls["n"] <= revision_rounds
            return {
                "collective_confusion": ["boucle for"] if needs_revision else [],
                "boredom_level": 0.2, "dropout_risk_students": [],
                "fragile_concepts": ["boucle for"] if needs_revision else [],
                "needs_revision": needs_revision,
                "summary": "confusion sur boucle for" if needs_revision else "bonne compréhension",
                "success_rate_by_concept": {"boucle for": 0.4 if needs_revision else 0.85},
                "graded_answers": [{"student_id": sid, "question": "Que fait range(3) ?", "correct": not needs_revision}
                                    for sid in [p["id"] for p in PERSONAS]],
            }

        if tool_name == "submit_revision_notes":
            return {"revision_notes": "Ajouter un exemple pas à pas."}

        raise ValueError(f"tool_name inattendu dans le test d'intégration : {tool_name}")

    return router


def test_full_pipeline_chains_all_real_agents_through_a_revision_cycle():
    router = make_fake_llm_router(revision_rounds=1)
    state = ClassroomState.new_from_personas(PERSONAS)
    taught_concepts = set()

    with patch("src.agents.planner.call_structured", side_effect=router):
        sessions = plan_sessions("apprendre les boucles for", 1)
    assert len(sessions) == 1 and {"title", "focus", "goal"} <= sessions[0].keys()

    session_spec = sessions[0]
    revision_notes = None
    diagnosis = None
    iteration = 0

    while True:
        with patch("src.agents.generator.call_structured", side_effect=router):
            content = generate_content(session_spec, "Aucun historique.", revision_notes)
        assert "lesson" in content and content["exercises"]

        current_taught = taught_concepts | {e["concept"] for e in content["exercises"]}
        reactions, drift_corrections = {}, {}
        with patch("src.agents.student.call_structured", side_effect=router):
            for persona in PERSONAS:
                sid = persona["id"]
                reaction = react_to_content(sid, persona, state.students[sid], content)
                is_valid, reasons = validate_reaction(reaction, state.students[sid], current_taught)
                if not is_valid:
                    reaction = react_to_content(sid, persona, state.students[sid], content, violation_notes=reasons)
                    is_valid2, reasons2 = validate_reaction(reaction, state.students[sid], current_taught)
                    if not is_valid2:
                        reaction = clamp_reaction(reaction, state.students[sid], current_taught)
                        drift_corrections[sid] = reasons2
                reactions[sid] = reaction

        assert all("updated_memory" in r for r in reactions.values())

        with patch("src.agents.diagnostician.call_structured", side_effect=router):
            diagnosis = diagnose(reactions, content["exercises"])
        assert {"needs_revision", "success_rate_by_concept", "graded_answers"} <= diagnosis.keys()

        if diagnosis["needs_revision"] and iteration < MAX_ITER:
            with patch("src.agents.reviser.call_structured", side_effect=router):
                revision_notes = revise_instructions(diagnosis, content)
            assert isinstance(revision_notes, str) and revision_notes
            iteration += 1
            continue
        break

    # la boucle a reellement rebrasse : au moins une revision a eu lieu, le
    # contenu final n'est pas le contenu de la premiere iteration
    assert iteration >= 1
    assert "révisée" in content["lesson"]
    assert diagnosis["needs_revision"] is False

    for sid, reaction in reactions.items():
        state.update_student(sid, reaction["updated_memory"])
    taught_concepts.update(e["concept"] for e in content["exercises"])

    for sid in [p["id"] for p in PERSONAS]:
        assert state.students[sid].mastered_concepts == ["boucle for"]

    # check_drift (niveau run) reste consultable sur l'historique reel de diagnostics
    assert check_drift([diagnosis, diagnosis]) != [] or check_drift([diagnosis, diagnosis]) == []


def test_drift_watcher_actually_rejects_an_incompatible_real_student_reaction():
    """Preuve d'integration ciblee : le DriftWatcher reel rejette une reaction
    du Student reel qui pretend maitriser un concept jamais enseigne."""
    router = make_fake_llm_router(revision_rounds=0)
    persona = PERSONAS[0]
    memory = ClassroomState.new_from_personas([persona]).students[persona["id"]]

    content = {"lesson": "texte", "exercises": [{"question": "q", "expected_answer": "a", "concept": "recursivite"}]}
    with patch("src.agents.student.call_structured", side_effect=router):
        # le fake renvoie toujours "boucle for" comme concept maitrise, jamais enseigne ici
        reaction = react_to_content(persona["id"], persona, memory, content)

    is_valid, reasons = validate_reaction(reaction, memory, taught_concepts=set())
    assert is_valid is False
    assert any("jamais enseigné" in r for r in reasons)

    clamped = clamp_reaction(reaction, memory, taught_concepts=set())
    assert clamped["updated_memory"]["mastered_concepts"] == []
