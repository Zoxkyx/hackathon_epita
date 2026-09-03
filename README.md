# La Classe Fantôme

Hackathon EPITA — IA Agentique au service de l'éducation.

**La Classe Fantôme ne teste pas un contenu pédagogique, elle teste sa demi-vie.** Un enseignant décrit un objectif ; une classe synthétique de 5 élèves-agents à mémoire longitudinale suit 5 séances générées automatiquement, répond réellement aux exercices, et le système mesure ce qui est encore retenu plusieurs séances plus tard — pas seulement ce qui plaît à l'instant T.

## Pourquoi ce projet

Le patron "génère → critique → révise" est connu (façon Reflexion) et ne suffit pas à différencier un système de génération pédagogique. Ce qu'aucun système de ce type ne fait : mesurer la rétention réelle d'une population synthétique dans le temps, avec un contrôle déterministe de la plausibilité de cette simulation (le DriftWatcher). Le détail du raisonnement et des arbitrages est dans [`docs/architecture.md`](docs/architecture.md).

## Architecture en un coup d'œil

6 rôles d'agents, une boucle explicite (pas de framework d'agents) :

```
Objectif enseignant
  → Planner : découpe en 5 séances
  → validation humaine du plan de séances
  → pour chaque séance :
       → Generator : rédige leçon + exercices (concept + réponse attendue)
       → Élèves-agents (parallèles) : répondent aux exercices, réagissent, mettent à jour leur mémoire
       → DriftWatcher : valide la plausibilité de chaque réaction (rejeu ou correction si besoin)
       → Diagnostician : corrige les réponses, calcule un taux de réussite par concept, diagnostique la classe
       → si besoin de révision : Reviser → nouvelles instructions → nouvelle itération
       → sinon : mémoire persistante mise à jour, snapshot de la séance
  → rapport de run (Markdown + JSON)
```

| Agent | Rôle | LLM ? |
|---|---|---|
| Planner | Découpe l'objectif en 5 séances | oui |
| Generator | Rédige leçon + exercices | oui |
| Élève-agent (×5) | Répond aux exercices, réagit, évolue | oui (parallélisé) |
| Diagnostician | Corrige les réponses, taux de réussite, diagnostic qualitatif | oui |
| Reviser | Traduit un diagnostic en instructions de révision | oui |
| DriftWatcher | Valide la plausibilité de la simulation (3 règles déterministes) | non |

Deux canaux de signal ne sont jamais confondus : le Diagnostician déclenche une révision de **contenu** ; le DriftWatcher ne modifie jamais le contenu, il rejoue ou corrige une **réaction d'élève**, ou remonte un avertissement de trajectoire dans le rapport.

## Stack technique

- Python 3.11+
- SDK `anthropic` — appels via tool use structuré (`input_schema`), jamais de parsing de texte JSON par regex ; cache de prompt sur les system prompts des élèves-agents
- `python-dotenv` pour la configuration locale
- `pytest` pour les tests
- Persistance en fichiers JSON (`data/`) — pas de base de données
- Aucun framework d'agents (pas de LangChain/LangGraph)

## Structure du projet

```
classe-fantome/
├── README.md
├── .env.example
├── requirements.txt              # dépendances runtime
├── requirements-dev.txt          # + pytest
├── main.py                       # CLI
├── src/
│   ├── config.py                 # modèle LLM, N_SESSIONS=5, MAX_ITER=2
│   ├── llm.py                    # wrapper tool-use structuré + cache de prompt
│   ├── fake_agents.py            # implémentations hors-ligne (mode --fake)
│   ├── agents/
│   │   ├── planner.py
│   │   ├── generator.py
│   │   ├── student.py
│   │   ├── diagnostician.py
│   │   ├── reviser.py
│   │   └── drift_watcher.py      # sans LLM
│   ├── memory/
│   │   └── classroom_state.py
│   ├── orchestrator.py
│   └── report.py
├── data/
│   ├── personas/                 # profils élèves à méprises caractéristiques
│   └── runs/                     # sorties de run (ignoré par git)
├── tests/
└── docs/
    ├── architecture.md           # spécification complète, positionnement, limites
    ├── repartition-equipe.md     # qui construit quoi
    └── superpowers/plans/        # plan d'implémentation détaillé (tâches, code de référence)
```

## Installation

```bash
git clone https://github.com/Zoxkyx/hackathon_epita.git
cd hackathon_epita
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env             # puis renseigner ANTHROPIC_API_KEY
```

## Utilisation

**Mode hors-ligne (sans clé API, quelques secondes)** — pour développer/tester l'orchestration :

```bash
python main.py --objective "faire comprendre les boucles for/while à des débutants" --fake --auto-approve
```

**Mode réel** — demande confirmation du plan de séances avant de lancer la génération :

```bash
python main.py --objective "faire comprendre les boucles for/while à des débutants en programmation, niveau lycée"
```

Options :
- `--fake` : utilise les agents hors-ligne (`src/fake_agents.py`), aucun appel réseau
- `--auto-approve` : saute la validation humaine du plan de séances

Chaque run écrit `data/runs/<run_id>/run_log.json` (trace complète) et `data/runs/<run_id>/report.md` (rapport lisible : contenu avant/après révision, taux de réussite par concept, trajectoire mémoire par séance, corrections DriftWatcher).

## Tests

```bash
python -m pytest -v
```

Tous les tests d'agents mockent les appels LLM (`unittest.mock.patch` sur `call_structured`) — aucune clé API n'est nécessaire pour faire passer la suite.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — spécification complète, positionnement, règles du DriftWatcher, limites et protocole de validation
- [`docs/repartition-equipe.md`](docs/repartition-equipe.md) — répartition des rôles pour l'équipe
- [`docs/superpowers/plans/2026-09-03-classe-fantome.md`](docs/superpowers/plans/2026-09-03-classe-fantome.md) — plan d'implémentation détaillé, tâche par tâche, avec code de référence

## Limites connues

Les élèves-agents sont des caricatures produites par le LLM, pas de vrais apprenants ; le Generator et les élèves partagent le même modèle, qui peut donc se juger complaisamment lui-même. Ces limites sont assumées et détaillées, avec un protocole de validation proposé, dans `docs/architecture.md`.

## Livrable

Le seul livrable noté est un rapport PDF — pas de démo live devant jury. La priorité va à l'originalité de l'architecture agentique, pas à l'exhaustivité fonctionnelle ni au polish visuel.
