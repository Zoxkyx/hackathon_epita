from src.llm import call_structured

PLANNER_TOOL_NAME = "submit_session_plan"
PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "focus": {"type": "string"},
                    "goal": {"type": "string"},
                },
                "required": ["title", "focus", "goal"],
            },
        }
    },
    "required": ["sessions"],
}

PLANNER_SYSTEM = (
    "Tu es Planner, un agent pédagogique. Tu découpes un objectif d'enseignant "
    "en une séquence de séances progressives et courtes."
)


def plan_sessions(objective: str, n_sessions: int) -> list:
    user_prompt = (
        f"Objectif de l'enseignant : {objective}\n"
        f"Découpe cet objectif en exactement {n_sessions} séances progressives."
    )
    result = call_structured(PLANNER_SYSTEM, user_prompt, PLANNER_TOOL_NAME, PLANNER_SCHEMA)
    return result["sessions"]
