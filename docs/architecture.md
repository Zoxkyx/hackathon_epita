# La Classe Fantôme — Architecture (Phase 2)

## Context

Hackathon EPITA "IA Agentique au service de l'éducation", 48h, notation uniquement sur l'innovation/originalité de l'idée et de l'architecture agentique (pas de benchmark). Livrable final : un rapport PDF uniquement — pas de démo live devant jury. L'équipe a validé la piste **"La Classe Fantôme"** en Phase 1 (idéation) : un enseignant décrit un objectif pédagogique, et une classe synthétique d'élèves-agents à mémoire persistante teste, critique et fait évoluer le contenu généré sur plusieurs cycles simulés, jusqu'à obtenir un contenu qui tient dans la durée (pas seulement à l'instant T).

L'objectif de cette phase est de définir l'architecture avant tout code. Comme le seul livrable est un PDF, la priorité technique est de produire un système qui **tourne réellement** et génère des traces exploitables (transcripts, évolution de la mémoire des élèves-agents, contenu avant/après révision) à intégrer comme preuves dans le rapport — pas une interface polie.

## Spécification technique

**Entrée :** un objectif pédagogique en langage naturel donné par l'enseignant (ex: "faire comprendre les boucles for/while à des débutants en programmation, niveau lycée").

**Sortie :** un pack de contenu pédagogique (leçons + exercices) pour N séances simulées, plus un rapport de run (JSON + Markdown) documentant tout le processus : ce qui a été généré, comment la classe synthétique a réagi, ce qui a été révisé, comment la mémoire des élèves-agents a évolué dans le temps.

**Boucle centrale (perception → planification → action, autonome) :**

```
Objectif enseignant
   → Planner : découpe l'objectif en N séances (specs courtes)
   → pour chaque séance (séquentiel) :
        iteration = 0
        → Generator(spec séance, mémoire classe, notes de révision) → contenu
        → chaque Élève-agent(persona, mémoire perso, contenu) → réaction
        → Diagnostician(toutes les réactions) → rapport de santé de classe
        → DriftWatcher(rapport de santé, historique) → anomalies éventuelles
        → si problèmes détectés ET iteration < MAX_ITER :
             Reviser(rapport de santé, contenu) → notes de révision
             iteration += 1 → retour au Generator
          sinon :
             contenu de la séance figé
             mise à jour de la mémoire persistante de chaque élève-agent
   → après toutes les séances : compilation du rapport de run
```

Le forgetting (oubli) et la progression ne sont pas calculés par une formule : chaque élève-agent reçoit son propre état mémoire à chaque séance et décide lui-même, via son prompt de persona, ce qu'il a retenu/oublié/comment il se sent — c'est un comportement émergent du LLM, pas un script déterministe. C'est le cœur de l'originalité : la classe synthétique a une vraie histoire.

## Agents & rôles

| Agent | Rôle | Appels LLM |
|---|---|---|
| **Planner** | Découpe l'objectif enseignant en séquence de N séances (specs courtes) | 1 par run |
| **Generator** | Rédige/révise le contenu (leçon + exercices) d'une séance | 1 par itération |
| **Élève-agent** (×N profils : rapide, en difficulté, distrait, moyen, anxieux) | Réagit au contenu selon sa persona et sa mémoire persistante ; met à jour lui-même sa mémoire | 1 par élève par itération |
| **Diagnostician** | Agrège les réactions de tous les élèves en signaux exploitables (confusion collective, ennui, décrochage, concepts fragiles) | 1 par itération |
| **Reviser** | Traduit le rapport de santé en instructions concrètes de révision pour le Generator | 1 par itération, si problème détecté |
| **Drift Watcher** | Vérifie que le comportement de la classe reste plausible (pas de blocage, pas de progrès artificiel) ; règles simples, pas de LLM | 0 (heuristique) |

Aucun orchestrateur "chef" implicite au sens agent-LLM : l'**orchestrateur** (`orchestrator.py`) est du code Python explicite qui séquence ces appels — les agents eux-mêmes ne se pilotent pas entre eux, ce qui garde le système traçable et débogable en 48h.

## Modèle de mémoire persistante (élève-agent)

État JSON par élève-agent, mis à jour à la fin de chaque séance :

```json
{
  "profile": "en difficulté",
  "mastered_concepts": ["variables"],
  "shaky_concepts": ["boucle for"],
  "forgotten_concepts": [],
  "engagement_trend": [0.8, 0.6],
  "history_notes": "résumé libre porté d'une séance à l'autre"
}
```

## Stack technique proposée

- **Python 3.11+** — prototypage rapide, JSON natif, pas de build.
- **Anthropic API** (SDK `anthropic`) — un seul modèle pour tous les agents par défaut (simplicité), configurable dans `config.py`.
- **Pas de framework d'agents** (pas de LangChain/LangGraph) — orchestration en Python simple, pour rester lisible et explicable dans le rapport.
- **Persistance en fichiers JSON** (`data/runs/`) — pas de base de données, inutile pour 48h.
- **Génération du rapport** : compilation Markdown à partir des logs de run (`report.py`), converti en PDF par l'équipe (pandoc ou export manuel) — hors scope du code agentique.

**Dépendances validées :**
- `anthropic` (SDK officiel, appels LLM)
- `python-dotenv` (chargement de la clé API depuis `.env`)

Aucune autre dépendance prévue.

## Arborescence de projet prévue

```
classe-fantome/
├── README.md
├── .env.example
├── requirements.txt
├── main.py                      # CLI: python main.py --objective "..."
├── src/
│   ├── config.py                 # modèle LLM, MAX_ITER, N_SESSIONS
│   ├── llm.py                    # wrapper appels Anthropic + parsing JSON
│   ├── agents/
│   │   ├── planner.py
│   │   ├── generator.py
│   │   ├── student.py            # classe Élève-agent + personas
│   │   ├── diagnostician.py
│   │   ├── reviser.py
│   │   └── drift_watcher.py      # heuristique, pas de LLM
│   ├── memory/
│   │   └── classroom_state.py    # état mémoire élèves, load/save JSON
│   ├── orchestrator.py           # boucle principale séances × itérations
│   └── report.py                 # compile le run log en rapport Markdown
└── data/
    ├── personas/                 # définitions des profils élèves (JSON)
    └── runs/                     # logs de run + contenu généré
```

## Vérification

- Lancer `python main.py --objective "<objectif test>"` avec une vraie clé API et vérifier qu'un run complet (N séances × itérations) se termine sans erreur.
- Inspecter `data/runs/<run_id>/` : le contenu de chaque séance doit montrer au moins un cycle de révision (contenu avant/après notes du Reviser).
- Vérifier que la mémoire d'au moins un élève-agent montre un effet d'oubli ou de progression entre deux séances (preuve de la mémoire persistante évolutive).
- Vérifier que `report.py` produit un Markdown exploitable, à convertir en PDF pour le rapport final.
