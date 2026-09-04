import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from src.agents.diagnostician import diagnose
from src.agents.drift_watcher import check_drift, clamp_reaction, validate_reaction
from src.agents.generator import generate_content
from src.agents.planner import plan_sessions
from src.agents.reviser import revise_instructions
from src.agents.student import react_to_content
from src.config import MAX_ITER, N_SESSIONS
from src.memory.classroom_state import ClassroomState


def summarize_classroom(state: ClassroomState) -> str:
    parts = []
    for sid, mem in state.students.items():
        parts.append(
            f"{sid} ({mem.profile}): maîtrise={mem.mastered_concepts}, "
            f"fragile={mem.shaky_concepts}, oublié={mem.forgotten_concepts}"
        )
    return " | ".join(parts) if parts else "Aucun historique."


def _get_validated_reaction(sid, persona, memory, content, current_taught_concepts, student_react):
    reaction = student_react(sid, persona, memory, content)
    is_valid, reasons = validate_reaction(reaction, memory, current_taught_concepts)
    drift_correction = None
    if not is_valid:
        reaction = student_react(sid, persona, memory, content, violation_notes=reasons)
        is_valid2, reasons2 = validate_reaction(reaction, memory, current_taught_concepts)
        if not is_valid2:
            reaction = clamp_reaction(reaction, memory, current_taught_concepts)
            drift_correction = reasons2
    return sid, reaction, drift_correction


def run(objective: str, personas: list,
        planner=plan_sessions, generator=generate_content, student_react=react_to_content,
        diagnostician=diagnose, reviser=revise_instructions, drift_check=check_drift,
        n_sessions: int = N_SESSIONS, max_iter: int = MAX_ITER, session_plan_hook=None) -> dict:
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    state = ClassroomState.new_from_personas(personas)
    sessions_spec = planner(objective, n_sessions)
    if session_plan_hook is not None:
        sessions_spec = session_plan_hook(sessions_spec)

    run_log = {"run_id": run_id, "objective": objective, "sessions": []}
    diagnosis_history = []
    taught_concepts = set()

    for session_spec in sessions_spec:
        iteration = 0
        revision_notes = None
        session_log = {"spec": session_spec, "iterations": []}
        reactions = {}

        while True:
            content = generator(session_spec, summarize_classroom(state), revision_notes)
            current_taught_concepts = taught_concepts | {e["concept"] for e in content["exercises"]}

            with ThreadPoolExecutor(max_workers=max(len(personas), 1)) as executor:
                futures = [
                    executor.submit(
                        _get_validated_reaction, persona["id"], persona, state.students[persona["id"]],
                        content, current_taught_concepts, student_react,
                    )
                    for persona in personas
                ]
                results = [f.result() for f in futures]

            reactions = {}
            drift_corrections = {}
            for sid, reaction, drift_correction in results:
                reactions[sid] = reaction
                if drift_correction:
                    drift_corrections[sid] = drift_correction

            diagnosis = diagnostician(reactions, content["exercises"])
            diagnosis_history.append(diagnosis)
            run_drift_flags = drift_check(diagnosis_history)

            session_log["iterations"].append({
                "iteration": iteration,
                "content": content,
                "reactions": reactions,
                "diagnosis": diagnosis,
                "drift_corrections": drift_corrections,
                "run_drift_flags": run_drift_flags,
                "revision_notes_used": revision_notes,
            })

            if diagnosis.get("needs_revision") and iteration < max_iter:
                revision_notes = reviser(diagnosis, content)
                iteration += 1
                continue
            break

        for sid, reaction in reactions.items():
            state.update_student(sid, reaction["updated_memory"])
        taught_concepts.update(e["concept"] for e in content["exercises"])

        session_log["final_content"] = content
        session_log["memory_snapshot"] = state.to_dict()
        run_log["sessions"].append(session_log)

    run_log["final_classroom_state"] = state.to_dict()
    return run_log
