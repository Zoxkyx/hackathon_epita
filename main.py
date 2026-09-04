import argparse
import json
import os

from dotenv import load_dotenv

from src.orchestrator import run
from src.report_html import save_html_report


def load_personas(path="data/personas/default.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def confirm_session_plan(sessions):
    print("Plan de séances proposé par le Planner :")
    for i, s in enumerate(sessions, start=1):
        print(f"  {i}. {s['title']} — {s['goal']}")
    answer = input("Valider ce plan ? [O/n] ").strip().lower()
    if answer in ("", "o", "oui", "y", "yes"):
        return sessions
    raise SystemExit("Plan de séances refusé par l'enseignant. Run interrompu.")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="La Classe Fantôme")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--fake", action="store_true", help="Mode hors-ligne, sans appel LLM réel")
    parser.add_argument("--auto-approve", action="store_true", help="Ne pas demander confirmation du plan de séances")
    args = parser.parse_args()

    personas = load_personas()

    kwargs = {}
    if args.fake:
        from src import fake_agents
        kwargs.update({
            "planner": fake_agents.fake_plan_sessions,
            "generator": fake_agents.fake_generate_content,
            "student_react": fake_agents.fake_react_to_content,
            "diagnostician": fake_agents.fake_diagnose,
            "reviser": fake_agents.fake_revise_instructions,
        })
    if not args.auto_approve:
        kwargs["session_plan_hook"] = confirm_session_plan

    run_log = run(args.objective, personas, **kwargs)

    run_dir = f"data/runs/{run_log['run_id']}"
    os.makedirs(run_dir, exist_ok=True)
    with open(f"{run_dir}/run_log.json", "w", encoding="utf-8") as f:
        json.dump(run_log, f, ensure_ascii=False, indent=2)
    save_html_report(run_log, f"{run_dir}/report.html")
    print(f"Run terminé : {run_dir}")


if __name__ == "__main__":
    main()
