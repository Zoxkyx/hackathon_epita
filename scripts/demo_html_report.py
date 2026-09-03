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
import zlib

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


# Contenu écrit séance par séance. Chaque note du Reviser part d'une méprise réelle
# déclarée dans data/personas/default.json, pour que la maquette ressemble à ce que
# produirait la vraie boucle plutôt qu'à un gabarit rempli.
SESSIONS = {
    "variables": {
        "title": "Ce qu'une variable désigne",
        "goal": "Comprendre qu'une variable étiquette une valeur",
        "v1": "Une variable est une étiquette collée sur une valeur, pas une boîte qui la contient. "
              "On écrit age = 17 pour coller l'étiquette age sur 17, et age = 18 la recolle ailleurs "
              "sans rien détruire.",
        "question": "Après a = 3 puis b = a puis a = 5, que vaut b ?",
        "answer": "3",
    },
    "boucle for": {
        "title": "Parcourir dans les deux sens",
        "goal": "Comprendre que for parcourt une séquence connue à l'avance",
        "v1": "La boucle for parcourt une séquence connue à l'avance. for i in range(5) répète cinq fois, "
              "avec i qui prend successivement les valeurs 0 à 4.",
        "question": "Écris une boucle qui affiche 5, 4, 3, 2, 1 dans cet ordre.",
        "answer": "for i in range(5, 0, -1)",
        "note": "Trois élèves sur cinq ont répondu que range ne sait aller que vers le haut : la méprise "
                "du profil moyen est confirmée par leurs réponses. Ajouter un exemple à pas négatif avant "
                "l'exercice, et leur faire écrire la valeur de i à chaque tour.",
        "gain": 0.35,
        "v2": "La boucle for parcourt une séquence connue à l'avance, dans un sens comme dans l'autre. "
              "range(5) monte de 0 à 4, range(4, -1, -1) redescend de 4 à 0 : le troisième argument est "
              "le pas, et rien n'interdit qu'il soit négatif.",
    },
    "boucle while": {
        "title": "La boucle qui ne sait pas quand s'arrêter",
        "goal": "Distinguer while de for par la condition d'arrêt",
        "v1": "La boucle while répète tant qu'une condition reste vraie. Contrairement au for, elle ne "
              "sait pas d'avance combien de tours elle fera.",
        "question": "Pourquoi while x > 0 peut-il ne jamais s'arrêter ?",
        "answer": "si rien dans le corps ne diminue x",
        "note": "Les élèves rapides s'ennuient sur un exercice sans risque d'erreur, et le profil anxieux "
                "n'a pas exécuté son code. Faire écrire volontairement une boucle infinie, leur faire "
                "prédire ce qui se passe, puis la réparer : l'erreur devient l'objet du cours.",
        "gain": 0.22,
        "v2": "La boucle while répète tant qu'une condition reste vraie, et c'est là son danger : si rien "
              "dans le corps ne rapproche la condition de False, elle tourne indéfiniment. Écrire une "
              "boucle qui ne s'arrête pas, puis la réparer, montre mieux qu'un cours ce qui l'arrête.",
    },
    "conditions imbriquées": {
        "title": "L'indentation décide",
        "goal": "Rattacher chaque ligne au bon if",
        "v1": "Une condition imbriquée n'est qu'une condition posée à l'intérieur d'une autre. Le piège "
              "n'est pas la logique, c'est l'indentation : c'est elle, et rien d'autre, qui décide de "
              "quel if dépend chaque ligne.",
        "question": "Déplacer le else de deux espaces vers la gauche : à quel if se rattache-t-il ?",
        "answer": "au if extérieur",
    },
    "fonctions": {
        "title": "Des variables qui ne vivent qu'à l'intérieur",
        "goal": "Comprendre la portée des paramètres",
        "v1": "Une fonction met un morceau de code de côté sous un nom, pour le rappeler plus tard sans "
              "le réécrire.",
        "question": "Une fonction modifie son paramètre n. La variable passée en argument change-t-elle ?",
        "answer": "non",
        "note": "La réussite sur les variables est retombée à 30 % cinq séances après leur introduction. "
                "Rattacher les fonctions à un rappel actif de ce concept : faire manipuler des paramètres, "
                "qui sont des variables locales, au lieu d'énoncer la règle de portée.",
        "gain": 0.14,
        "v2": "Une fonction met un morceau de code de côté sous un nom. Ses paramètres sont des variables "
              "qui n'existent qu'à l'intérieur d'elle : les modifier ne change rien dehors. C'est "
              "l'étiquette de la première séance, mais collée sur une table qu'on jette en sortant.",
    },
}


# Chaque profil décale sa probabilité de réussite autour du taux du concept, sans
# la décider : un profil solide se trompe parfois, un profil fragile réussit parfois.
# Un ordre strict produirait des 100 % et des 0 %, exactement le genre de classe
# trop lisse que le DriftWatcher est censé signaler.
SKILL_OFFSET = {
    "eleve_rapide": 0.25,
    "eleve_moyen": 0.05,
    "eleve_distrait": -0.05,
    "eleve_anxieux": -0.10,
    "eleve_difficulte": -0.20,
}


def graded_answers(success_rate_by_concept, question, session_idx):
    graded = []
    for concept, rate in success_rate_by_concept.items():
        for sid, offset in SKILL_OFFSET.items():
            probability = min(max(rate + offset, 0.08), 0.92)
            # tirage déterministe : la démo doit être reproductible d'un run à l'autre
            seed = f"{sid}|{concept}|{session_idx}|{question}"
            draw = (zlib.crc32(seed.encode("utf-8")) % 1000) / 1000
            graded.append({"student_id": sid, "question": question, "correct": draw < probability})
    return graded


def session_log(i, concept, revised, drift_correction=False):
    spec = SESSIONS[concept]
    success_rate_v1 = {c: rates[i] for c, rates in RETENTION.items() if i in rates}

    iterations = [{
        "iteration": 0,
        "content": {
            "lesson": spec["v1"],
            "exercises": [{"question": spec["question"], "expected_answer": spec["answer"], "concept": concept}],
        },
        "diagnosis": {
            "summary": f"Confusion notable sur {concept}, plusieurs élèves décrochent.",
            "success_rate_by_concept": success_rate_v1,
            "graded_answers": graded_answers(success_rate_v1, spec["question"], i),
        },
        "drift_corrections": {
            "eleve_rapide": ["Concept 'récursivité' marqué maîtrisé mais jamais enseigné."]
        } if drift_correction else {},
        "run_drift_flags": [],
        "revision_notes_used": None,
    }]

    if revised:
        success_rate_v2 = dict(success_rate_v1)
        success_rate_v2[concept] = min(success_rate_v1.get(concept, 0.3) + spec["gain"], 0.95)
        iterations.append({
            "iteration": 1,
            "content": {
                "lesson": spec["v2"],
                "exercises": [{"question": spec["question"], "expected_answer": spec["answer"], "concept": concept}],
            },
            "diagnosis": {
                "summary": f"Nette amélioration sur {concept} après réécriture.",
                "success_rate_by_concept": success_rate_v2,
                "graded_answers": graded_answers(success_rate_v2, spec["question"], i + 100),
            },
            "drift_corrections": {},
            "run_drift_flags": [] if i != 5 else [
                "eleve_rapide : engagement au maximum sur 3 itérations consécutives sans aucune erreur, "
                "profil trop lisse pour être plausible."
            ],
            "revision_notes_used": spec["note"],
        })

    return {
        "spec": {"title": spec["title"], "focus": concept, "goal": spec["goal"]},
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
