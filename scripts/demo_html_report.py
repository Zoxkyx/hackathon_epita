"""Génère un exemple de rapport HTML avec des données synthétiques réalistes
sur 5 séances, pour évaluer le rendu visuel sans attendre un vrai run.

Simule un Generator qui retesterait périodiquement les anciens concepts (ce que
le vrai Generator ne fait pas encore spontanément — voir la note dans
docs/repartition-equipe.md à ce sujet) pour montrer à quoi ressemble une vraie
courbe de rétention multi-points.

Usage : .venv/Scripts/python.exe scripts/demo_html_report.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report_html import save_html_report

STUDENTS = ["eleve_rapide", "eleve_difficulte", "eleve_distrait", "eleve_moyen", "eleve_anxieux"]
PROFILES = ["rapide", "en difficulté", "distrait", "moyen", "anxieux"]
CONCEPTS = ["variables", "boucle for", "boucle while", "conditions imbriquées", "fonctions"]

# taux de réussite mesuré pour chaque concept, à chaque séance où il est retesté
# (séance d'introduction + séances suivantes) : simule l'effet d'oubli/consolidation
RETENTION = {
    "variables": {1: 0.40, 2: 0.55, 3: 0.45, 4: 0.35, 5: 0.30},
    "boucle for": {2: 0.30, 3: 0.75, 4: 0.60, 5: 0.55},
    "boucle while": {3: 0.50, 4: 0.65, 5: 0.60},
    "conditions imbriquées": {4: 0.35, 5: 0.50},
    "fonctions": {5: 0.45},
}


def memory_snapshot(session_idx):
    snapshot = {}
    for i, sid in enumerate(STUDENTS):
        mastered = [c for c in CONCEPTS[:session_idx] if RETENTION[c].get(session_idx, 1.0) >= 0.5]
        shaky = [c for c in CONCEPTS[:session_idx] if c not in mastered]
        forgotten = ["variables"] if session_idx >= 4 and i in (1, 3) else []
        mastered = [c for c in mastered if c not in forgotten]
        shaky = [c for c in shaky if c not in forgotten]
        snapshot[sid] = {
            "profile": PROFILES[i],
            "mastered_concepts": mastered,
            "shaky_concepts": shaky,
            "forgotten_concepts": forgotten,
        }
    return snapshot


def session_log(i, concept, revised, drift_correction=False):
    success_rate_v1 = {c: rates[i] for c, rates in RETENTION.items() if i in rates}
    diagnosis_v1 = {
        "summary": f"Confusion notable sur {concept}, plusieurs élèves décrochent.",
        "success_rate_by_concept": success_rate_v1,
    }

    iterations = [{
        "iteration": 0,
        "content": {
            "lesson": f"Introduction au concept « {concept} » avec un exemple simple et un contre-exemple.",
            "exercises": [{"question": f"Applique {concept} sur cet exemple.", "expected_answer": "réponse attendue", "concept": concept}],
        },
        "diagnosis": diagnosis_v1,
        "drift_corrections": {"eleve_rapide": ["Concept 'x' marqué maîtrisé mais jamais enseigné."]} if drift_correction else {},
        "run_drift_flags": [],
        "revision_notes_used": None,
    }]

    if revised:
        success_rate_v2 = dict(success_rate_v1)
        success_rate_v2[concept] = min(success_rate_v1.get(concept, 0.3) + 0.3, 0.95)
        iterations.append({
            "iteration": 1,
            "content": {
                "lesson": f"Reprise de « {concept} » avec un exemple pas à pas et une analogie concrète, exercice progressif ajouté.",
                "exercises": [{"question": f"Applique {concept} sur un cas progressif.", "expected_answer": "réponse attendue", "concept": concept}],
            },
            "diagnosis": {
                "summary": f"Nette amélioration sur {concept} après simplification.",
                "success_rate_by_concept": success_rate_v2,
            },
            "drift_corrections": {},
            "run_drift_flags": [] if i != 5 else ["Ennui constant et maximal sur plusieurs itérations — signal potentiellement irréaliste."],
            "revision_notes_used": "Simplifier l'exemple d'introduction, ajouter un exercice intermédiaire avant l'exercice final.",
        })

    return {
        "spec": {"title": concept.capitalize(), "focus": concept, "goal": f"Comprendre {concept}"},
        "iterations": iterations,
        "final_content": iterations[-1]["content"],
        "memory_snapshot": memory_snapshot(i),
    }


def build_demo_run_log():
    sessions = [
        session_log(1, "variables", revised=False),
        session_log(2, "boucle for", revised=True, drift_correction=True),
        session_log(3, "boucle while", revised=True),
        session_log(4, "conditions imbriquées", revised=False),
        session_log(5, "fonctions", revised=True),
    ]
    return {
        "run_id": "demo-2026-09-03",
        "objective": "faire comprendre les boucles for/while à des débutants en programmation, niveau lycée",
        "sessions": sessions,
        "final_classroom_state": memory_snapshot(5),
    }


if __name__ == "__main__":
    out_path = os.path.join("data", "runs", "demo-2026-09-03", "report.html")
    save_html_report(build_demo_run_log(), out_path)
    print(f"Rapport de démo généré : {out_path}")
