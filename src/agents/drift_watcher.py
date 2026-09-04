def validate_reaction(reaction: dict, previous_memory, taught_concepts: set) -> tuple:
    reasons = []
    updated = reaction["updated_memory"]

    newly_mastered = set(updated["mastered_concepts"]) - set(previous_memory.mastered_concepts)
    for concept in newly_mastered:
        if concept not in taught_concepts:
            reasons.append(f"Concept '{concept}' marqué maîtrisé mais jamais enseigné.")

    previously_known = set(previous_memory.mastered_concepts) | set(previous_memory.shaky_concepts)
    for concept in updated["forgotten_concepts"]:
        if concept not in previously_known:
            reasons.append(f"Concept '{concept}' marqué oublié mais n'était pas acquis auparavant.")

    if previous_memory.engagement_trend and updated["engagement_trend"]:
        prev_eng = previous_memory.engagement_trend[-1]
        new_eng = updated["engagement_trend"][-1]
        if abs(new_eng - prev_eng) > 0.4:
            reasons.append(f"Engagement passé de {prev_eng} à {new_eng} (variation > 0.4) en une séance.")

    return (len(reasons) == 0, reasons)


def clamp_reaction(reaction: dict, previous_memory, taught_concepts: set) -> dict:
    updated = dict(reaction["updated_memory"])
    updated["mastered_concepts"] = [
        c for c in updated["mastered_concepts"]
        if c in taught_concepts or c in previous_memory.mastered_concepts
    ]
    previously_known = set(previous_memory.mastered_concepts) | set(previous_memory.shaky_concepts)
    updated["forgotten_concepts"] = [c for c in updated["forgotten_concepts"] if c in previously_known]

    if previous_memory.engagement_trend and updated["engagement_trend"]:
        prev_eng = previous_memory.engagement_trend[-1]
        new_eng = updated["engagement_trend"][-1]
        if abs(new_eng - prev_eng) > 0.4:
            clamped_value = round(prev_eng + (0.4 if new_eng > prev_eng else -0.4), 10)
            updated["engagement_trend"] = updated["engagement_trend"][:-1] + [clamped_value]

    clamped_reaction = dict(reaction)
    clamped_reaction["updated_memory"] = updated
    return clamped_reaction


def check_drift(diagnosis_history: list) -> list:
    flags = []
    if len(diagnosis_history) >= 2:
        last_two = diagnosis_history[-2:]
        if all(d["needs_revision"] for d in last_two) and last_two[0]["summary"] == last_two[1]["summary"]:
            flags.append("Stagnation détectée : la classe ne progresse pas malgré les révisions.")
        if all(d["boredom_level"] >= 0.9 for d in last_two):
            flags.append("Ennui constant et maximal sur plusieurs itérations — signal potentiellement irréaliste.")
        if (all(not d["fragile_concepts"] and not d["collective_confusion"] for d in last_two)
                and all(d["boredom_level"] < 0.1 for d in last_two)):
            flags.append("Classe parfaite sans aucune friction — signal potentiellement irréaliste.")
    return flags