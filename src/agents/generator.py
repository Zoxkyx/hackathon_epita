from src.llm import call_structured

GENERATOR_TOOL_NAME = "submit_session_content"
GENERATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "lesson": {"type": "string"},
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "expected_answer": {"type": "string"},
                    "concept": {"type": "string"},
                },
                "required": ["question", "expected_answer", "concept"],
            },
        },
    },
    "required": ["lesson", "exercises"],
}

GENERATOR_SYSTEM = (
    "Tu es Generator, un agent qui rédige du contenu pédagogique (leçon + exercices). "
    "Chaque exercice doit cibler un concept nommé explicitement et fournir la réponse attendue. "
    "Ajoute périodiquement un exercice de rappel sur un concept des séances précédentes."
)


def generate_content(session_spec: dict, classroom_summary: str, revision_notes) -> dict:
    user_prompt = (
        f"Séance à préparer : {session_spec['title']}\n"
        f"Objectif de la séance : {session_spec['goal']}\n"
        f"Focus : {session_spec['focus']}\n"
        f"État actuel de la classe : {classroom_summary}\n"
    )
    if revision_notes:
        user_prompt += f"\nNotes de révision à prendre en compte : {revision_notes}\n"
    return call_structured(GENERATOR_SYSTEM, user_prompt, GENERATOR_TOOL_NAME, GENERATOR_SCHEMA)
