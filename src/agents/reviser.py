from src.llm import call_structured

REVISER_TOOL_NAME = "submit_revision_notes"
REVISER_SCHEMA = {
    "type": "object",
    "properties": {"revision_notes": {"type": "string"}},
    "required": ["revision_notes"],
}

REVISER_SYSTEM = (
    "Tu es Reviser, un agent qui traduit un diagnostic de classe en instructions concrètes et "
    "actionnables de révision pour l'agent qui génère le contenu."
)


def revise_instructions(diagnosis: dict, content: dict) -> str:
    user_prompt = (
        f"Diagnostic de la classe : {diagnosis}\n"
        f"Contenu actuel :\nLeçon : {content['lesson']}\nExercices : {content['exercises']}\n"
    )
    result = call_structured(REVISER_SYSTEM, user_prompt, REVISER_TOOL_NAME, REVISER_SCHEMA)
    return result["revision_notes"]
