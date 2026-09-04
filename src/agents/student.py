from src.llm import call_structured

STUDENT_TOOL_NAME = "submit_reaction"
STUDENT_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "given_answer": {"type": "string"},
                },
                "required": ["question", "given_answer"],
            },
        },
        "reaction_text": {"type": "string"},
        "updated_memory": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "mastered_concepts": {"type": "array", "items": {"type": "string"}},
                "shaky_concepts": {"type": "array", "items": {"type": "string"}},
                "forgotten_concepts": {"type": "array", "items": {"type": "string"}},
                "engagement_trend": {"type": "array", "items": {"type": "number"}},
                "history_notes": {"type": "string"},
            },
            "required": [
                "profile", "mastered_concepts", "shaky_concepts",
                "forgotten_concepts", "engagement_trend", "history_notes",
            ],
        },
    },
    "required": ["answers", "reaction_text", "updated_memory"],
}

STUDENT_SYSTEM_TEMPLATE = (
    'Tu es un élève simulé nommé {student_id}, de profil "{profile}".\n'
    "Méprises caractéristiques de ce profil : {misconceptions}.\n"
    "Tu reçois un contenu de cours et ta propre mémoire (ce que tu maîtrises, ce qui est fragile, "
    "ce que tu as oublié). Réponds à chaque exercice en restant cohérent avec tes méprises si elles "
    "s'appliquent encore, sauf si le cours vient de les corriger clairement. Décide toi-même, selon "
    'ta persona et ta mémoire, ce que tu retiens, oublies ou consolides dans "updated_memory".'
)


def react_to_content(student_id: str, persona: dict, memory, content: dict, violation_notes=None) -> dict:
    misconceptions = ", ".join(persona.get("misconceptions", [])) or "aucune en particulier"
    system = STUDENT_SYSTEM_TEMPLATE.format(
        student_id=student_id, profile=persona["profile"], misconceptions=misconceptions
    )
    visible_exercises = [{"question": e["question"], "concept": e["concept"]} for e in content["exercises"]]
    user_prompt = (
        f"Ta mémoire actuelle : {memory.to_dict()}\n"
        f"Leçon : {content['lesson']}\n"
        f"Exercices : {visible_exercises}\n"
    )
    if violation_notes:
        user_prompt += (
            f"\nTa précédente réponse a été jugée invraisemblable pour les raisons suivantes : "
            f"{violation_notes}. Corrige ta réponse en conséquence.\n"
        )
    return call_structured(system, user_prompt, STUDENT_TOOL_NAME, STUDENT_SCHEMA, cacheable_system=True)