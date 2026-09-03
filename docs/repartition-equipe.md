# Répartition en 5 — La Classe Fantôme

Référence unique : `docs/superpowers/plans/2026-09-03-classe-fantome.md` (contient, pour chaque tâche, les fichiers exacts, les interfaces exactes — signatures, schémas JSON — et le code de référence). `docs/architecture.md` donne le pourquoi.

**Propriété clé pour paralléliser dès maintenant :** tous les tests des agents (Tâches 1, 3, 4, 5) mockent `call_structured` (`unittest.mock.patch`). Personne n'a besoin d'attendre que `llm.py` (Tâche 1) soit fini pour écrire et faire passer ses propres tests — chacun code contre le contrat d'interface fixé dans le plan, pas contre l'implémentation réelle des autres. Seule la Tâche 8 (smoke test réel) a besoin que tout soit vraiment assemblé.

## Qui fait quoi

| Personne | Tâche(s) | Fichiers | Dépend de | Bloque |
|---|---|---|---|---|
| **P1** | Tâche 1 — LLM wrapper (tool use + cache) | `src/llm.py`, `src/config.py` | rien | Intégration réelle (Tâche 8) uniquement |
| **P2** | Tâche 2 — Mémoire, personas, agents hors-ligne | `src/memory/classroom_state.py`, `data/personas/default.json`, `src/fake_agents.py` | rien | Tâche 7 (orchestrateur) |
| **P3** | Tâche 3 — Planner + Generator | `src/agents/planner.py`, `src/agents/generator.py` | contrat de `llm.py` (pas l'implémentation) | Tâche 7 |
| **P4** | Tâche 4 — Élève-agent + Tâche 6 — DriftWatcher | `src/agents/student.py`, `src/agents/drift_watcher.py` | contrat de `llm.py` (Tâche 4 seulement) ; Tâche 6 ne dépend de rien (pas de LLM) | Tâche 7 |
| **P5** | Tâche 5 — Diagnostician + Reviser | `src/agents/diagnostician.py`, `src/agents/reviser.py` | contrat de `llm.py` | Tâche 7 |

**Tout le monde démarre en parallèle dès maintenant**, chacun sur sa branche, en suivant son bloc de tâche dans le plan (steps TDD : écrire le test, vérifier qu'il échoue, implémenter, vérifier qu'il passe, commit).

## Intégration (une fois 1-6 mergés)

- **Tâche 7** — Orchestrateur + CLI (`src/orchestrator.py`, `main.py`) : à faire par la personne qui termine en premier (probablement P1 ou P2, tâches les plus courtes), une fois les agents mergés. C'est le seul point qui assemble tout.
- **Tâche 8** — Rapport + smoke test (`src/report.py`, `docs/smoke-test-notes.md`) : en binôme, en dernier, une fois la Tâche 7 mergée. Nécessite une vraie clé `ANTHROPIC_API_KEY`.

## Règles pour éviter les conflits

- Chaque tâche touche des fichiers disjoints (voir tableau) — peu de risque de conflit de merge.
- Ne pas modifier les schémas JSON (`*_SCHEMA`) ni les signatures de fonctions définis dans le plan sans le signaler aux autres : ce sont les contrats dont dépendent les tâches suivantes (Interfaces > Produces / Consumes dans chaque tâche du plan).
- `docs/architecture.md` et le plan ne bougent plus sauf découverte bloquante en cours de route — si un contrat doit changer, le signaler à toute l'équipe avant de merger.
