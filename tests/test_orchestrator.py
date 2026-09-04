from src.orchestrator import run


def fake_planner(objective, n_sessions):
    return [{"title": f"Séance {i + 1}", "focus": "c1", "goal": "g"} for i in range(n_sessions)]


def fake_generator(session_spec, classroom_summary, revision_notes):
    return {
        "lesson": f"contenu ({revision_notes})",
        "exercises": [{"question": "q", "expected_answer": "a", "concept": "c1"}],
    }


def make_fake_student_react():
    def fake_student_react(student_id, persona, memory, content, violation_notes=None):
        return {
            "answers": [{"question": "q", "given_answer": "a"}],
            "reaction_text": "ok",
            "updated_memory": {
                "profile": persona["profile"],
                "mastered_concepts": ["c1"],
                "shaky_concepts": [],
                "forgotten_concepts": [],
                "engagement_trend": [0.8],
                "history_notes": "ok",
            },
        }
    return fake_student_react


def make_fake_diagnostician(needs_revision_sequence):
    calls = {"n": 0}

    def fake_diagnostician(reactions, exercises):
        idx = min(calls["n"], len(needs_revision_sequence) - 1)
        needs_revision = needs_revision_sequence[idx]
        calls["n"] += 1
        return {
            "collective_confusion": [], "boredom_level": 0.1, "dropout_risk_students": [],
            "fragile_concepts": [], "needs_revision": needs_revision, "summary": f"état {idx}",
            "success_rate_by_concept": {"c1": 1.0},
            "graded_answers": [{"student_id": sid, "question": "q", "correct": True} for sid in reactions],
        }
    return fake_diagnostician


def fake_reviser(diagnosis, content):
    return "simplifier"


def fake_drift_check(history):
    return []


def test_run_stops_reviser_loop_when_needs_revision_false():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([True, False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=2,
    )
    session = run_log["sessions"][0]
    assert len(session["iterations"]) == 2
    assert session["iterations"][0]["revision_notes_used"] is None
    assert session["iterations"][1]["revision_notes_used"] == "simplifier"


def test_run_stops_at_max_iter():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([True, True, True]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=1,
    )
    assert len(run_log["sessions"][0]["iterations"]) == 2


def test_run_updates_classroom_memory_and_snapshot():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=2,
    )
    assert run_log["final_classroom_state"]["e1"]["mastered_concepts"] == ["c1"]
    assert run_log["sessions"][0]["memory_snapshot"]["e1"]["mastered_concepts"] == ["c1"]


def test_run_clamps_implausible_mastery_via_drift_watcher():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]

    def student_claims_untaught_mastery(student_id, persona, memory, content, violation_notes=None):
        return {
            "answers": [{"question": "q", "given_answer": "a"}],
            "reaction_text": "ok",
            "updated_memory": {
                "profile": persona["profile"],
                "mastered_concepts": ["concept_jamais_enseigne"],
                "shaky_concepts": [], "forgotten_concepts": [], "engagement_trend": [], "history_notes": "",
            },
        }

    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=student_claims_untaught_mastery,
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=0,
    )
    corrections = run_log["sessions"][0]["iterations"][0]["drift_corrections"]
    assert "e1" in corrections
    assert run_log["final_classroom_state"]["e1"]["mastered_concepts"] == []


def test_session_plan_hook_can_edit_sessions():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]

    def hook(sessions):
        return [{**sessions[0], "title": "Titre édité"}]

    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=0, session_plan_hook=hook,
    )
    assert run_log["sessions"][0]["spec"]["title"] == "Titre édité"
