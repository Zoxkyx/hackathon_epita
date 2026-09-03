def fake_plan_sessions(objective: str, n_sessions: int) -> list:
    return [
        {"title": f"Séance {i + 1} (fake)", "focus": "focus fictif", "goal": f"objectif fictif {i + 1}"}
        for i in range(n_sessions)
    ]


def fake_generate_content(session_spec: dict, classroom_summary: str, revision_notes) -> dict:
    suffix = " (révisé)" if revision_notes else ""
    return {
        "lesson": f"Leçon fictive pour {session_spec['title']}{suffix}",
        "exercises": [
            {"question": "Question fictive ?", "expected_answer": "Réponse fictive", "concept": session_spec["focus"]}
        ],
    }


def fake_react_to_content(student_id: str, persona: dict, memory, content: dict, violation_notes=None) -> dict:
    concept = content["exercises"][0]["concept"]
    return {
        "answers": [{"question": e["question"], "given_answer": e["expected_answer"]} for e in content["exercises"]],
        "reaction_text": f"Réaction fictive de {student_id}",
        "updated_memory": {
            "profile": persona["profile"],
            "mastered_concepts": list(memory.mastered_concepts) + [concept],
            "shaky_concepts": list(memory.shaky_concepts),
            "forgotten_concepts": list(memory.forgotten_concepts),
            "engagement_trend": list(memory.engagement_trend) + [0.7],
            "history_notes": "historique fictif",
        },
    }


def fake_diagnose(reactions: dict, exercises: list) -> dict:
    return {
        "collective_confusion": [],
        "boredom_level": 0.2,
        "dropout_risk_students": [],
        "fragile_concepts": [],
        "needs_revision": False,
        "summary": "diagnostic fictif",
        "success_rate_by_concept": {e["concept"]: 1.0 for e in exercises},
        "graded_answers": [
            {"student_id": sid, "question": e["question"], "correct": True}
            for sid in reactions
            for e in exercises
        ],
    }


def fake_revise_instructions(diagnosis: dict, content: dict) -> str:
    return "note de révision fictive"
