from src.report_html import render_html_report, save_html_report


def make_fake_run_log():
    def session(i, concept, before_rate, after_rate, revised, drift_reason=None):
        drift_corrections = {"eleve_rapide": [drift_reason]} if drift_reason else {}
        return {
            "spec": {"title": f"Séance {i}", "focus": concept, "goal": f"comprendre {concept}"},
            "iterations": [
                {
                    "iteration": 0,
                    "content": {"lesson": f"Leçon v1 sur {concept}", "exercises": [
                        {"question": "q", "expected_answer": "a", "concept": concept}
                    ]},
                    "diagnosis": {"summary": "confusion initiale", "success_rate_by_concept": {concept: before_rate}},
                    "drift_corrections": drift_corrections,
                    "run_drift_flags": [],
                    "revision_notes_used": None,
                },
                {
                    "iteration": 1,
                    "content": {"lesson": f"Leçon v2 (révisée) sur {concept}", "exercises": [
                        {"question": "q", "expected_answer": "a", "concept": concept}
                    ]},
                    "diagnosis": {"summary": "ça va mieux", "success_rate_by_concept": {concept: after_rate}},
                    "drift_corrections": {},
                    "run_drift_flags": ["Classe parfaite sans aucune friction — signal potentiellement irréaliste."] if not revised else [],
                    "revision_notes_used": "simplifier l'exemple" if revised else None,
                },
            ],
            "final_content": {"lesson": f"Leçon v2 (révisée) sur {concept}", "exercises": []},
            "memory_snapshot": {
                "eleve_rapide": {"profile": "rapide", "mastered_concepts": [concept], "shaky_concepts": [], "forgotten_concepts": []},
                "eleve_difficulte": {"profile": "en difficulté", "mastered_concepts": [], "shaky_concepts": [concept], "forgotten_concepts": []},
            },
        }

    return {
        "run_id": "test-run-html",
        "objective": "apprendre les boucles for/while",
        "sessions": [
            session(1, "boucle for", 0.3, 0.9, revised=True, drift_reason="Concept 'x' marqué maîtrisé mais jamais enseigné."),
            session(2, "boucle while", 0.5, 0.5, revised=False),
        ],
        "final_classroom_state": {
            "eleve_rapide": {"profile": "rapide", "mastered_concepts": ["boucle for", "boucle while"], "shaky_concepts": [], "forgotten_concepts": []},
            "eleve_difficulte": {"profile": "en difficulté", "mastered_concepts": [], "shaky_concepts": ["boucle while"], "forgotten_concepts": ["boucle for"]},
        },
    }


def test_render_html_report_contains_key_sections():
    report = render_html_report(make_fake_run_log())
    assert "apprendre les boucles for/while" in report
    assert "test-run-html" in report
    assert "Leçon v1 sur boucle for" in report
    assert "Leçon v2 (révisée) sur boucle for" in report
    assert "simplifier l&#x27;exemple" in report
    assert "R1 — maîtrise d&#x27;un concept non enseigné" in report
    assert "Classe parfaite" in report
    assert "boucle for" in report
    assert "boucle while" in report
    assert "eleve_rapide" in report
    assert "<svg" in report


def test_render_html_report_handles_empty_sessions():
    run_log = {"run_id": "empty", "objective": "obj", "sessions": [], "final_classroom_state": {}}
    report = render_html_report(run_log)
    assert "empty" in report.lower() or "Pas assez" in report or "Pas de trajectoire" in report


def test_save_html_report_writes_file(tmp_path):
    path = tmp_path / "sub" / "report.html"
    save_html_report(make_fake_run_log(), str(path))
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "<!doctype html>" in content.lower()
