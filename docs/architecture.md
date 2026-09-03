# La Classe Fantôme — Architecture (Phase 2, révisée)

## Context

Hackathon EPITA "IA Agentique au service de l'éducation", 48h, notation uniquement sur l'innovation/originalité de l'idée et de l'architecture agentique (pas de benchmark). Livrable final : un rapport PDF uniquement — pas de démo live devant jury.

**La Classe Fantôme ne teste pas un contenu, elle teste sa demi-vie.** Le patron génère → critique → révise est connu (façon Reflexion) et ne suffit pas à différencier le projet. Ce qu'aucun système de génération pédagogique ne fait : mesurer ce qu'une population d'élèves synthétiques à mémoire longitudinale retient encore trois séances plus tard, pas ce qui plaît à l'instant T. C'est cette mesure de rétention dans le temps qui est le sujet du projet ; l'architecture (génération, diagnostic, révision) est à son service, pas l'inverse.

## Spécification technique

**Entrée :** un objectif pédagogique en langage naturel donné par l'enseignant.

**Sortie :** un pack de contenu pédagogique pour 5 séances simulées, plus un rapport de run (JSON + Markdown) documentant : ce qui a été généré, comment la classe a répondu (avec taux de réussite mesuré par concept, pas seulement une impression), ce qui a été révisé, et la trajectoire de mémoire de chaque élève séance par séance.

**Boucle centrale :**

```
Objectif enseignant
   → Planner : découpe l'objectif en 5 séances
   → validation humaine du plan de séances (l'enseignant confirme ou refuse, cf. section Validation humaine)
   → pour chaque séance (séquentiel) :
        iteration = 0
        → Generator(spec séance, mémoire classe, notes de révision) → contenu (leçon + exercices,
          chaque exercice porte un concept nommé et une réponse attendue)
        → en parallèle, chaque Élève-agent(persona, mémoire perso, contenu) → réponses aux exercices
          + réaction + mémoire mise à jour
        → chaque réaction passe par le DriftWatcher (validate_reaction) : si elle viole une règle de
          plausibilité, l'élève est resollicité une fois ; si ça persiste, la réaction est corrigée
          automatiquement (clamp_reaction) et l'incident est loggé
        → Diagnostician(réponses corrigées, réactions) → taux de réussite par concept + diagnostic
          qualitatif (confusion, ennui, décrochage) + besoin de révision
        → check_drift (niveau run) : signale les trajectoires globales invraisemblables (stagnation,
          classe parfaite...) comme avertissement dans le rapport, sans jamais déclencher de révision
        → si besoin de révision ET iteration < MAX_ITER :
             Reviser(diagnostic, contenu) → notes de révision
             iteration += 1 → retour au Generator
          sinon :
             contenu de la séance figé, mémoire persistante mise à jour, snapshot mémoire de la séance
   → après toutes les séances : compilation du rapport de run
```

Le forgetting et la progression ne sont pas calculés par une formule côté élève-agent : chaque élève reçoit sa mémoire et décide, via sa persona (méprises caractéristiques, pas une simple humeur), ce qu'il retient ou oublie — comportement émergent du LLM. Ce qui est déterministe, en revanche, c'est le contrôle de plausibilité de ce comportement (DriftWatcher) : c'est le seul composant non-LLM du système, et c'est volontaire — c'est là que le système affirme de la rigueur.

## Deux canaux de signal, jamais confondus

- **Diagnostician → Reviser** : mesure la qualité du contenu (confusion, ennui, taux de réussite). Un signal ici déclenche une révision du contenu.
- **DriftWatcher** : mesure la plausibilité de la simulation elle-même (un élève ne peut pas maîtriser un concept jamais enseigné, ni oublier un concept jamais acquis, ni voir son engagement bondir de plus de 0.4 en une séance). Un signal ici ne modifie jamais le contenu : soit il invalide et rejoue la réaction d'un élève, soit il est remonté comme avertissement dans le rapport (`check_drift`, niveau run — stagnation, classe parfaite sans friction, etc.).

## Règles déterministes du DriftWatcher

| Règle | Contrôle | Action si violée |
|---|---|---|
| R1 | Un concept ne peut être marqué "maîtrisé" que s'il a été enseigné (dans les exercices de la séance en cours ou d'une séance précédente) | Rejeu (1x) puis correction automatique |
| R2 | Un concept ne peut être marqué "oublié" que s'il était auparavant "maîtrisé" ou "fragile" | Rejeu (1x) puis correction automatique |
| R3 | L'engagement ne peut pas varier de plus de 0.4 entre deux séances consécutives | Rejeu (1x) puis clamp à ±0.4 |

Chaque déclenchement est loggé dans le run (`drift_corrections` par itération) — matière pour un tableau du rapport final ("règles déclenchées, combien de fois, sur quels élèves").

## Agents & rôles (6, inchangé)

| Agent | Rôle | Appels LLM |
|---|---|---|
| **Planner** | Découpe l'objectif en 5 séances | 1 par run |
| **Generator** | Rédige leçon + exercices (question, réponse attendue, concept ciblé) | 1 par itération |
| **Élève-agent** (×5 profils, méprises caractéristiques) | Répond aux exercices, réagit, met à jour sa propre mémoire | 1 par élève par itération (parallélisé) |
| **Diagnostician** | Corrige les réponses (given vs expected), calcule un taux de réussite par concept, diagnostique confusion/ennui/décrochage | 1 par itération |
| **Reviser** | Traduit le diagnostic en instructions concrètes pour le Generator | 1 par itération si besoin de révision |
| **DriftWatcher** | Valide la plausibilité de chaque réaction (règles déterministes) + signale les trajectoires globales suspectes | 0 (heuristique pure) |

## Personas : méprises précises, pas des humeurs

Chaque persona porte une liste `misconceptions` de méprises nommées (ex: "confond affectation et égalité", "pense qu'une boucle for ne peut pas décrémenter") plutôt qu'un simple trait de caractère. Ça rend les notes de révision actionnables et l'oubli observable sur un concept précis, pas une ambiance générale.

## Modèle de mémoire persistante (élève-agent)

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

`engagement_trend` reste un signal narratif auto-rapporté par le LLM, pas la métrique principale (une droite de flottants produite par un LLM est trop lisse pour être crédible). La métrique objective centrale est le **taux de réussite par concept** calculé par le Diagnostician à partir de vraies réponses aux exercices — c'est elle qui alimente la courbe de compréhension sur 5 séances, la figure qui porte le rapport.

## Validation humaine

L'enseignant ne disparaît pas après avoir donné son objectif : le plan de séances produit par le Planner lui est présenté et doit être validé (ou refusé) avant toute génération de contenu. Implémenté comme un hook optionnel côté CLI (`main.py`), pas dans l'orchestrateur lui-même, pour garder `orchestrator.run()` testable sans interaction stdin. Un flag `--auto-approve` permet de sauter cette étape pour des runs automatisés.

## Limites et protocole de validation (à assumer frontalement dans le rapport)

- **Les élèves-agents sont des caricatures du LLM, pas de vrais apprenants.** Un LLM qui joue "l'élève en difficulté" reproduit la représentation que le modèle se fait d'un élève en difficulté — le système optimise le contenu contre un miroir, pas contre la réalité.
- **Biais d'auto-évaluation** : le Generator et les élèves-agents utilisent le même modèle. Le système peut produire des révisions complaisantes (le modèle "valide" ce que le modèle a produit).
- **Protocole de validation proposé (non implémenté en 48h)** : rejouer un sous-ensemble des séances générées avec de vrais élèves (ou enseignants en proxy), comparer le taux de réussite réel par concept au taux prédit par le Diagnostician, et mesurer l'écart. Un système qui connaît sa propre faiblesse et la documente vaut mieux qu'un système qui la découvre en Q&A devant le jury.

## Mode hors-ligne (développement)

`src/fake_agents.py` fournit des implémentations déterministes de chaque agent (aucun appel réseau), injectées via les paramètres de `orchestrator.run(...)` (déjà conçu par injection de dépendances). Activé via `python main.py --fake` — permet de tester toute la boucle d'orchestration en quelques secondes, sans clé API. Sans ce mode, un run réel (5 élèves × 5 séances × jusqu'à 3 itérations, appels séquentiels) prendrait environ 30 minutes, incompatible avec un cycle de debug en 48h — d'où aussi la parallélisation des appels élèves (indépendants au sein d'une itération) via `concurrent.futures.ThreadPoolExecutor`.

## Stack technique

- **Python 3.11+**, aucun framework d'agents (pas de LangChain/LangGraph) — orchestration explicite en `orchestrator.py`.
- **SDK `anthropic`**, appels via **tool use structuré** (`input_schema` + `tool_choice`) plutôt que parsing de texte JSON par regex — plus robuste. Modèle unique par défaut `claude-sonnet-5`, configurable via `CLASSE_FANTOME_MODEL`.
- **Cache de prompt** (`cache_control: ephemeral`) sur les system prompts des élèves-agents, qui se répètent à chaque itération.
- **Persistance en fichiers JSON** (`data/runs/`, `data/personas/`) — pas de base de données.
- **Dépendances runtime :** `anthropic`, `python-dotenv`. **Dépendance dev :** `pytest`.

## Arborescence de projet

```
classe-fantome/
├── README.md
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── main.py                      # CLI: python main.py --objective "..." [--fake] [--auto-approve]
├── src/
│   ├── config.py                 # modèle LLM, MAX_ITER, N_SESSIONS=5
│   ├── llm.py                    # wrapper tool-use structuré + cache de prompt
│   ├── fake_agents.py            # implémentations hors-ligne de chaque agent
│   ├── agents/
│   │   ├── planner.py
│   │   ├── generator.py
│   │   ├── student.py
│   │   ├── diagnostician.py      # inclut la correction des réponses et le taux de réussite
│   │   ├── reviser.py
│   │   └── drift_watcher.py      # validate_reaction, clamp_reaction, check_drift — sans LLM
│   ├── memory/
│   │   └── classroom_state.py
│   ├── orchestrator.py           # boucle principale, parallélisation, snapshots mémoire
│   └── report.py                 # rapport Markdown : diff avant/après, courbe de réussite, trajectoire mémoire
└── data/
    ├── personas/                 # profils avec méprises caractéristiques
    └── runs/
```

## Vérification

- `python main.py --objective "<test>" --fake --auto-approve` doit se terminer en quelques secondes.
- `python main.py --objective "<test>"` (mode réel) doit produire un run complet et demander confirmation du plan de séances.
- Inspecter `data/runs/<run_id>/run_log.json` : au moins une correction DriftWatcher ou un cycle de révision doit apparaître sur l'ensemble du run (sinon documenter pourquoi dans les notes de smoke test).
- Le taux de réussite par concept doit être présent et varier d'une séance à l'autre pour au moins un concept.
- `report.md` doit contenir la courbe de réussite, le diff de contenu avant/après révision, et la trajectoire mémoire par séance.
