from src.llm import call_structured

DIAGNOSTICIAN_TOOL_NAME = "submit_diagnosis"
DIAGNOSTICIAN_SCHEMA = {
    "type": "object",
    "properties": {
        "collective_confusion": {"type": "array", "items": {"type": "string"}},
        "boredom_level": {"type": "number"},
        "dropout_risk_students": {"type": "array", "items": {"type": "string"}},
        "fragile_concepts": {"type": "array", "items": {"type": "string"}},
        "needs_revision": {"type": "boolean"},
        "summary": {"type": "string"},
        "success_rate_by_concept": {"type": "object", "additionalProperties": {"type": "number"}},
        "graded_answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string"},
                    "question": {"type": "string"},
                    "correct": {"type": "boolean"},
                },
                "required": ["student_id", "question", "correct"],
            },
        },
    },
    "required": [
        "collective_confusion", "boredom_level", "dropout_risk_students", "fragile_concepts",
        "needs_revision", "summary", "success_rate_by_concept", "graded_answers",
    ],
}

DIAGNOSTICIAN_SYSTEM = (
    "Tu es Diagnostician. Tu reçois les réponses des élèves aux exercices ainsi que les réponses "
    "attendues, et leurs réactions. Corrige chaque réponse (correct/incorrect) en comparant "
    "given_answer à expected_answer (accepte les formulations équivalentes). Calcule un taux de "
    "réussite par concept (fraction de réponses correctes parmi les réponses concernant ce concept). "
    "Puis résume l'état qualitatif de la classe."
)


def diagnose(reactions: dict, exercises: list) -> dict:
    user_prompt = (
        f"Exercices avec réponse attendue : {exercises}\n"
        f"Réponses et réactions des élèves : {reactions}"
    )
    return call_structured(DIAGNOSTICIAN_SYSTEM, user_prompt, DIAGNOSTICIAN_TOOL_NAME, DIAGNOSTICIAN_SCHEMA)
