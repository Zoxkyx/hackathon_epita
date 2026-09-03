# Répartition en 5 — La Classe Fantôme

Référence unique pour le détail technique : `docs/superpowers/plans/2026-09-03-classe-fantome.md` (fichiers exacts, interfaces exactes — signatures, schémas JSON — et code de référence pour chaque tâche). `docs/architecture.md` donne le pourquoi. Certaines tâches du plan sont ici scindées entre deux rôles (ex: Tâche 3 séparée en Planner / Generator).

**Propriété clé pour paralléliser dès maintenant :** tous les tests des agents mockent `call_structured` (`unittest.mock.patch`). Personne n'a besoin d'attendre que `llm.py` (P1) soit fini pour écrire et faire passer ses propres tests — chacun code contre le contrat d'interface fixé dans le plan, pas contre l'implémentation réelle des autres. Seule l'intégration finale a besoin que tout soit vraiment assemblé.

## P1 — LLM wrapper (fondation)

**Fichiers :** `src/llm.py`, `src/config.py`
**À construire :** le point d'entrée unique vers l'API Anthropic — appel structuré via tool use (`call_structured`), gestion du cache de prompt (`cache_control`), configuration du modèle et des constantes (`N_SESSIONS`, `MAX_ITER`).
**Réf. plan :** Tâche 1.
**Dépend de :** rien. **Bloque :** l'intégration finale et le smoke test réel (tout le monde d'autre mocke cette couche).

## P2 — Mémoire, personas, agents hors-ligne

**Fichiers :** `src/memory/classroom_state.py`, `data/personas/default.json`, `src/fake_agents.py`
**À construire :** le modèle de mémoire persistante par élève (`StudentMemory`, `ClassroomState`, sauvegarde/chargement JSON), les 5 personas avec méprises caractéristiques, et les versions hors-ligne (fake) de chaque agent pour tester l'orchestration sans clé API.
**Réf. plan :** Tâche 2.
**Dépend de :** rien. **Bloque :** l'orchestrateur (P sur l'intégration).

## P3 — Planner

**Fichiers :** `src/agents/planner.py`
**À construire :** l'agent qui découpe l'objectif de l'enseignant en 5 séances progressives. Un seul appel LLM, un schéma JSON simple (`title`/`focus`/`goal` par séance), une fonction, un test.
**Réf. plan :** Tâche 3 (partie Planner uniquement, Steps 1-4).
**Dépend de :** le contrat de `llm.py` (pas son implémentation réelle — mocké dans les tests).
**Charge :** la plus légère des 5 parts — pas de logique de correction ni de règles déterministes, le plus petit schéma JSON du projet.

## P4 — Generator, Reviser, Diagnostician

**Fichiers :** `src/agents/generator.py`, `src/agents/reviser.py`, `src/agents/diagnostician.py`
**À construire :** Generator (rédige leçon + exercices avec réponse attendue et concept ciblé), Reviser (traduit un diagnostic en instructions de révision concrètes), Diagnostician (corrige les réponses des élèves, calcule un taux de réussite par concept, diagnostique confusion/ennui/décrochage — le schéma le plus riche des trois).
**Réf. plan :** Tâche 3 (partie Generator) + Tâche 5 (Diagnostician + Reviser) en entier.
**Dépend de :** le contrat de `llm.py`.

## P5 — Élève-agent et DriftWatcher

**Fichiers :** `src/agents/student.py`, `src/agents/drift_watcher.py`
**À construire :** l'élève-agent (répond aux exercices sans voir la réponse attendue, réagit selon sa persona et ses méprises, met à jour sa propre mémoire, gère le retry sur violation), et le DriftWatcher (les 3 règles déterministes de plausibilité — `validate_reaction`, `clamp_reaction`, `check_drift` — le seul composant du système sans LLM).
**Réf. plan :** Tâche 4 + Tâche 6.
**Dépend de :** le contrat de `llm.py` (Student uniquement — DriftWatcher ne dépend de rien).

## Intégration (une fois P1-P5 mergés)

- **Orchestrateur + CLI** (`src/orchestrator.py`, `main.py`, Tâche 7 du plan) : par la personne libre en premier une fois les 5 parts mergées. Le seul point qui assemble tout — parallélisation des appels élèves, intégration du DriftWatcher, snapshot mémoire par séance, validation humaine du plan de séances.
- **Rapport + smoke test réel** (`src/report.py`, `docs/smoke-test-notes.md`, Tâche 8 du plan) : en dernier, en binôme, avec une vraie clé `ANTHROPIC_API_KEY`.

## Règles pour éviter les conflits

- Chaque rôle touche des fichiers disjoints (voir ci-dessus) — peu de risque de conflit de merge.
- Ne pas modifier les schémas JSON (`*_SCHEMA`) ni les signatures de fonctions définis dans le plan sans le signaler aux autres : ce sont les contrats dont dépendent les rôles suivants (Interfaces > Produces / Consumes dans chaque tâche du plan).
- `docs/architecture.md` et le plan ne bougent plus sauf découverte bloquante en cours de route — si un contrat doit changer, le signaler à toute l'équipe avant de merger.
- Chacun travaille sur sa propre branche, suit le déroulé TDD de sa/ses tâche(s) dans le plan (écrire le test → vérifier qu'il échoue → implémenter → vérifier qu'il passe → commit), puis ouvre une PR vers `master`.
