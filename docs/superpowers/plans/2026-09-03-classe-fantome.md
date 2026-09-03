# La Classe Fantôme Implementation Plan (révisé)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire "La Classe Fantôme" : un enseignant décrit un objectif, une classe synthétique d'élèves-agents à mémoire longitudinale répond réellement à des exercices sur 5 séances simulées, et le système mesure ce qui est retenu dans la durée — pas seulement ce qui plaît à l'instant T.

**Architecture:** Orchestrateur Python explicite. Boucle par séance × itération : Planner (validé par l'enseignant) → Generator → Élèves-agents (parallèles, répondent aux exercices) → DriftWatcher (valide la plausibilité, rejoue/corrige si besoin) → Diagnostician (corrige les réponses, calcule un taux de réussite par concept, diagnostique la qualité) → [Reviser si besoin] → mémoire mise à jour + snapshot. `check_drift` signale les trajectoires globales suspectes dans le rapport sans jamais déclencher de révision.

**Tech Stack:** Python 3.11+, SDK `anthropic` (tool use structuré + cache de prompt), `python-dotenv`, `pytest`.

**Spec:** `docs/architecture.md`

## Global Constraints

- Python 3.11+, style simple, pas de commentaires sauf nécessité.
- Dépendances runtime : `anthropic`, `python-dotenv`. Dépendance dev : `pytest`.
- Modèle LLM unique par défaut `claude-sonnet-5`, configurable via `CLASSE_FANTOME_MODEL` (`src/config.py`).
- `N_SESSIONS = 5`, `MAX_ITER = 2` (voir `src/config.py`).
- Pas de framework d'agents. Toutes les réponses LLM passent par `src/llm.py::call_structured` (tool use, jamais de parsing de texte JSON par regex).
- Le Diagnostician (`needs_revision`) est le seul signal qui déclenche une révision de contenu. Le DriftWatcher (`validate_reaction`/`clamp_reaction`/`check_drift`) ne déclenche jamais de révision : il rejoue ou corrige une réaction d'élève, ou remonte un avertissement de trajectoire dans le rapport. Ne jamais faire dépendre `needs_revision` d'un signal DriftWatcher.
- Persistance uniquement en fichiers JSON (`data/runs/`, `data/personas/`).
- Aucun push git. Tout reste dans le worktree local de ce plan.
- Les tests d'agents qui appellent le LLM mockent `call_structured` ou `get_client` (`unittest.mock.patch`) — pas d'appel réseau réel dans la suite automatisée. Le seul test avec appel réel est la Tâche 8 (smoke test manuel).

---

### Task 1: Scaffold, config et wrapper LLM (tool use + cache de prompt)

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.env.example`
- Create: `src/__init__.py`, `src/config.py`, `src/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `src.config.MODEL_NAME: str`, `src.config.N_SESSIONS: int = 5`, `src.config.MAX_ITER: int = 2`
- Produces: `src.llm.call_structured(system_prompt: str, user_prompt: str, tool_name: str, input_schema: dict, max_tokens: int = 2000, cacheable_system: bool = False) -> dict`
- Produces: `src.llm.get_client()` (point d'extension pour les mocks de tests)

- [ ] **Step 1: Créer `requirements.txt`**

```
anthropic>=0.40.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: Créer `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0.0
```

- [ ] **Step 3: Créer `.env.example`**

```
ANTHROPIC_API_KEY=your-key-here
```

- [ ] **Step 4: Créer `src/__init__.py` (vide) et `src/config.py`**

```python
import os

MODEL_NAME = os.environ.get("CLASSE_FANTOME_MODEL", "claude-sonnet-5")
N_SESSIONS = 5
MAX_ITER = 2
```

- [ ] **Step 5: Écrire les tests dans `tests/test_llm.py`**

```python
from unittest.mock import MagicMock, patch

from src.llm import call_structured


class FakeBlock:
    def __init__(self, type, input=None):
        self.type = type
        self.input = input


def test_call_structured_extracts_tool_input():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("tool_use", input={"a": 1})]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        result = call_structured("system", "user", "my_tool", {"type": "object", "properties": {}})
    assert result == {"a": 1}
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "my_tool"}
    assert call_kwargs["system"] == "system"


def test_call_structured_raises_without_tool_use_block():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("text", input=None)]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        raised = False
        try:
            call_structured("system", "user", "my_tool", {})
        except ValueError:
            raised = True
        assert raised


def test_call_structured_uses_cache_control_when_cacheable():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("tool_use", input={})]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        call_structured("system text", "user", "my_tool", {}, cacheable_system=True)
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == [{"type": "text", "text": "system text", "cache_control": {"type": "ephemeral"}}]
```

- [ ] **Step 6: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.llm'`

- [ ] **Step 7: Implémenter `src/llm.py`**

```python
import os

import anthropic

from src.config import MODEL_NAME

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call_structured(system_prompt: str, user_prompt: str, tool_name: str, input_schema: dict,
                     max_tokens: int = 2000, cacheable_system: bool = False) -> dict:
    client = get_client()
    system = system_prompt
    if cacheable_system:
        system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[{"name": tool_name, "description": f"Retourne {tool_name}", "input_schema": input_schema}],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("Aucun bloc tool_use dans la réponse du modèle.")
```

- [ ] **Step 8: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_llm.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add requirements.txt requirements-dev.txt .env.example src/__init__.py src/config.py src/llm.py tests/test_llm.py
git commit -m "feat: scaffold, config and structured LLM tool-use wrapper"
```

---

### Task 2: Mémoire persistante, personas à méprises, agents hors-ligne

**Files:**
- Create: `src/memory/__init__.py`, `src/memory/classroom_state.py`
- Create: `data/personas/default.json`
- Create: `src/fake_agents.py`
- Test: `tests/test_classroom_state.py`, `tests/test_fake_agents.py`

**Interfaces:**
- Produces: `src.memory.classroom_state.StudentMemory` (dataclass : `profile: str, mastered_concepts: list, shaky_concepts: list, forgotten_concepts: list, engagement_trend: list, history_notes: str`; `to_dict()`, `from_dict(d)` classmethod)
- Produces: `src.memory.classroom_state.ClassroomState` (`ClassroomState(students: dict[str, StudentMemory])`, `new_from_personas(personas) -> ClassroomState`, `to_dict()`, `from_dict(d)`, `save(path)`, `load(path)`, `update_student(student_id, memory_update: dict)`)
- Produces: `data/personas/default.json` — 5 personas `{"id": str, "profile": str, "misconceptions": list[str]}`
- Produces: `src.fake_agents.fake_plan_sessions(objective, n_sessions) -> list`, `fake_generate_content(session_spec, classroom_summary, revision_notes) -> dict`, `fake_react_to_content(student_id, persona, memory, content, violation_notes=None) -> dict`, `fake_diagnose(reactions, exercises) -> dict`, `fake_revise_instructions(diagnosis, content) -> str` — mêmes contrats que les agents réels (Tasks 3-5), sans appel réseau

- [ ] **Step 1: Écrire les tests dans `tests/test_classroom_state.py`**

```python
from src.memory.classroom_state import ClassroomState, StudentMemory


def test_student_memory_roundtrip():
    mem = StudentMemory(profile="rapide", mastered_concepts=["a"])
    mem2 = StudentMemory.from_dict(mem.to_dict())
    assert mem2.profile == "rapide"
    assert mem2.mastered_concepts == ["a"]


def test_new_from_personas():
    personas = [
        {"id": "e1", "profile": "rapide", "misconceptions": []},
        {"id": "e2", "profile": "lent", "misconceptions": ["confond a et b"]},
    ]
    state = ClassroomState.new_from_personas(personas)
    assert set(state.students.keys()) == {"e1", "e2"}
    assert state.students["e1"].mastered_concepts == []


def test_update_student():
    state = ClassroomState.new_from_personas([{"id": "e1", "profile": "rapide", "misconceptions": []}])
    state.update_student("e1", {
        "profile": "rapide", "mastered_concepts": ["boucles"], "shaky_concepts": [],
        "forgotten_concepts": [], "engagement_trend": [0.8], "history_notes": "a bien suivi",
    })
    assert state.students["e1"].mastered_concepts == ["boucles"]


def test_save_and_load(tmp_path):
    state = ClassroomState.new_from_personas([{"id": "e1", "profile": "rapide", "misconceptions": []}])
    path = tmp_path / "state.json"
    state.save(str(path))
    loaded = ClassroomState.load(str(path))
    assert loaded.students["e1"].profile == "rapide"
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_classroom_state.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.memory'`

- [ ] **Step 3: Implémenter `src/memory/__init__.py` (vide) et `src/memory/classroom_state.py`**

```python
import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class StudentMemory:
    profile: str
    mastered_concepts: list = field(default_factory=list)
    shaky_concepts: list = field(default_factory=list)
    forgotten_concepts: list = field(default_factory=list)
    engagement_trend: list = field(default_factory=list)
    history_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StudentMemory":
        return cls(**d)


class ClassroomState:
    def __init__(self, students: dict):
        self.students = students

    @classmethod
    def new_from_personas(cls, personas: list) -> "ClassroomState":
        students = {p["id"]: StudentMemory(profile=p["profile"]) for p in personas}
        return cls(students)

    def to_dict(self) -> dict:
        return {sid: mem.to_dict() for sid, mem in self.students.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "ClassroomState":
        return cls({sid: StudentMemory.from_dict(mem) for sid, mem in d.items()})

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "ClassroomState":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def update_student(self, student_id: str, memory_update: dict) -> None:
        self.students[student_id] = StudentMemory.from_dict(memory_update)
```

- [ ] **Step 4: Créer `data/personas/default.json`**

```json
[
  {"id": "eleve_rapide", "profile": "rapide", "misconceptions": ["pense qu'optimiser trop tôt est toujours mieux"]},
  {"id": "eleve_difficulte", "profile": "en difficulté", "misconceptions": ["confond affectation (=) et égalité (==)"]},
  {"id": "eleve_distrait", "profile": "distrait", "misconceptions": ["oublie les cas limites (listes vides, zéro)"]},
  {"id": "eleve_moyen", "profile": "moyen", "misconceptions": ["pense qu'une boucle for ne peut pas décrémenter"]},
  {"id": "eleve_anxieux", "profile": "anxieux", "misconceptions": ["évite de tester son code par peur de se tromper"]}
]
```

- [ ] **Step 5: Lancer les tests classroom_state pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_classroom_state.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Écrire les tests dans `tests/test_fake_agents.py`**

```python
from src.fake_agents import (
    fake_diagnose,
    fake_generate_content,
    fake_plan_sessions,
    fake_react_to_content,
    fake_revise_instructions,
)
from src.memory.classroom_state import StudentMemory


def test_fake_plan_sessions_returns_n_sessions():
    sessions = fake_plan_sessions("objectif", 3)
    assert len(sessions) == 3
    for s in sessions:
        assert set(s.keys()) == {"title", "focus", "goal"}


def test_fake_generate_content_has_exercises_with_concept():
    session_spec = {"title": "S1", "focus": "boucles", "goal": "g"}
    content = fake_generate_content(session_spec, "resume", None)
    assert content["exercises"][0]["concept"] == "boucles"
    assert "expected_answer" in content["exercises"][0]


def test_fake_react_to_content_answers_and_masters_current_concept():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": []}
    memory = StudentMemory(profile="rapide")
    content = {"lesson": "l", "exercises": [{"question": "q", "expected_answer": "a", "concept": "boucles"}]}
    reaction = fake_react_to_content("e1", persona, memory, content)
    assert reaction["answers"][0]["question"] == "q"
    assert "boucles" in reaction["updated_memory"]["mastered_concepts"]


def test_fake_diagnose_returns_success_rate_per_concept():
    exercises = [{"question": "q", "expected_answer": "a", "concept": "boucles"}]
    result = fake_diagnose({"e1": {}}, exercises)
    assert result["success_rate_by_concept"]["boucles"] == 1.0
    assert result["needs_revision"] is False


def test_fake_revise_instructions_returns_string():
    assert isinstance(fake_revise_instructions({}, {}), str)
```

- [ ] **Step 7: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_fake_agents.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.fake_agents'`

- [ ] **Step 8: Implémenter `src/fake_agents.py`**

```python
def fake_plan_sessions(objective: str, n_sessions: int) -> list:
    return [
        {"title": f"Séance {i + 1} (fake)", "focus": "focus fictif", "goal": f"objectif fictif {i + 1}"}
        for i in range(n_sessions)
    ]


def fake_generate_content(session_spec: dict, classroom_summary: str, revision_notes) -> dict:
    suffix = " (révisé)" if revision_notes else ""
    return {
        "lesson": f"Leçon fictive pour {session_spec['title']}{suffix}",
        "exercises": [
            {"question": "Question fictive ?", "expected_answer": "Réponse fictive", "concept": session_spec["focus"]}
        ],
    }


def fake_react_to_content(student_id: str, persona: dict, memory, content: dict, violation_notes=None) -> dict:
    concept = content["exercises"][0]["concept"]
    return {
        "answers": [{"question": e["question"], "given_answer": e["expected_answer"]} for e in content["exercises"]],
        "reaction_text": f"Réaction fictive de {student_id}",
        "updated_memory": {
            "profile": persona["profile"],
            "mastered_concepts": list(memory.mastered_concepts) + [concept],
            "shaky_concepts": list(memory.shaky_concepts),
            "forgotten_concepts": list(memory.forgotten_concepts),
            "engagement_trend": list(memory.engagement_trend) + [0.7],
            "history_notes": "historique fictif",
        },
    }


def fake_diagnose(reactions: dict, exercises: list) -> dict:
    return {
        "collective_confusion": [],
        "boredom_level": 0.2,
        "dropout_risk_students": [],
        "fragile_concepts": [],
        "needs_revision": False,
        "summary": "diagnostic fictif",
        "success_rate_by_concept": {e["concept"]: 1.0 for e in exercises},
        "graded_answers": [
            {"student_id": sid, "question": e["question"], "correct": True}
            for sid in reactions
            for e in exercises
        ],
    }


def fake_revise_instructions(diagnosis: dict, content: dict) -> str:
    return "note de révision fictive"
```

- [ ] **Step 9: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_fake_agents.py -v`
Expected: PASS (5 tests)

- [ ] **Step 10: Commit**

```bash
git add src/memory/__init__.py src/memory/classroom_state.py data/personas/default.json src/fake_agents.py tests/test_classroom_state.py tests/test_fake_agents.py
git commit -m "feat: persistent memory model, misconception personas, offline fake agents"
```

---

### Task 3: Agents Planner et Generator (tool use)

**Files:**
- Create: `src/agents/__init__.py`, `src/agents/planner.py`, `src/agents/generator.py`
- Test: `tests/test_planner.py`, `tests/test_generator.py`

**Interfaces:**
- Consumes: `src.llm.call_structured` (Task 1)
- Produces: `src.agents.planner.plan_sessions(objective: str, n_sessions: int) -> list[dict]` — chaque dict : `title`, `focus`, `goal`
- Produces: `src.agents.generator.generate_content(session_spec: dict, classroom_summary: str, revision_notes: str | None) -> dict` — `{"lesson": str, "exercises": [{"question": str, "expected_answer": str, "concept": str}]}`

- [ ] **Step 1: Écrire le test dans `tests/test_planner.py`**

```python
from unittest.mock import patch

from src.agents.planner import plan_sessions


def test_plan_sessions_calls_call_structured_and_returns_sessions():
    fake_result = {"sessions": [{"title": "Intro", "focus": "bases", "goal": "comprendre X"}]}
    with patch("src.agents.planner.call_structured", return_value=fake_result) as mock_call:
        result = plan_sessions("Apprendre X", 1)
    assert result == fake_result["sessions"]
    args, kwargs = mock_call.call_args
    assert "Apprendre X" in args[1]
    assert "1" in args[1]
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_planner.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents'`

- [ ] **Step 3: Implémenter `src/agents/__init__.py` (vide) et `src/agents/planner.py`**

```python
from src.llm import call_structured

PLANNER_TOOL_NAME = "submit_session_plan"
PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "focus": {"type": "string"},
                    "goal": {"type": "string"},
                },
                "required": ["title", "focus", "goal"],
            },
        }
    },
    "required": ["sessions"],
}

PLANNER_SYSTEM = (
    "Tu es Planner, un agent pédagogique. Tu découpes un objectif d'enseignant "
    "en une séquence de séances progressives et courtes."
)


def plan_sessions(objective: str, n_sessions: int) -> list:
    user_prompt = (
        f"Objectif de l'enseignant : {objective}\n"
        f"Découpe cet objectif en exactement {n_sessions} séances progressives."
    )
    result = call_structured(PLANNER_SYSTEM, user_prompt, PLANNER_TOOL_NAME, PLANNER_SCHEMA)
    return result["sessions"]
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_planner.py -v`
Expected: PASS

- [ ] **Step 5: Écrire le test dans `tests/test_generator.py`**

```python
from unittest.mock import patch

from src.agents.generator import generate_content


def test_generate_content_first_pass_no_revision_notes():
    fake_result = {"lesson": "texte", "exercises": [{"question": "q", "expected_answer": "a", "concept": "c"}]}
    session_spec = {"title": "Intro", "focus": "bases", "goal": "comprendre X"}
    with patch("src.agents.generator.call_structured", return_value=fake_result) as mock_call:
        result = generate_content(session_spec, "Aucun historique.", None)
    assert result == fake_result
    args, kwargs = mock_call.call_args
    assert "Intro" in args[1]
    assert "Notes de révision" not in args[1]


def test_generate_content_includes_revision_notes():
    fake_result = {"lesson": "texte v2", "exercises": []}
    session_spec = {"title": "Intro", "focus": "bases", "goal": "comprendre X"}
    with patch("src.agents.generator.call_structured", return_value=fake_result) as mock_call:
        generate_content(session_spec, "resume", "simplifier l'exemple 2")
    args, kwargs = mock_call.call_args
    assert "simplifier l'exemple 2" in args[1]
```

- [ ] **Step 6: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_generator.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents.generator'`

- [ ] **Step 7: Implémenter `src/agents/generator.py`**

```python
from src.llm import call_structured

GENERATOR_TOOL_NAME = "submit_session_content"
GENERATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "lesson": {"type": "string"},
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "expected_answer": {"type": "string"},
                    "concept": {"type": "string"},
                },
                "required": ["question", "expected_answer", "concept"],
            },
        },
    },
    "required": ["lesson", "exercises"],
}

GENERATOR_SYSTEM = (
    "Tu es Generator, un agent qui rédige du contenu pédagogique (leçon + exercices). "
    "Chaque exercice doit cibler un concept nommé explicitement et fournir la réponse attendue."
)


def generate_content(session_spec: dict, classroom_summary: str, revision_notes) -> dict:
    user_prompt = (
        f"Séance à préparer : {session_spec['title']}\n"
        f"Objectif de la séance : {session_spec['goal']}\n"
        f"Focus : {session_spec['focus']}\n"
        f"État actuel de la classe : {classroom_summary}\n"
    )
    if revision_notes:
        user_prompt += f"\nNotes de révision à prendre en compte : {revision_notes}\n"
    return call_structured(GENERATOR_SYSTEM, user_prompt, GENERATOR_TOOL_NAME, GENERATOR_SCHEMA)
```

- [ ] **Step 8: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_generator.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add src/agents/__init__.py src/agents/planner.py src/agents/generator.py tests/test_planner.py tests/test_generator.py
git commit -m "feat: planner and generator agents (structured tool use)"
```

---

### Task 4: Agent Élève — répond aux exercices, méprises, retry sur violation

**Files:**
- Create: `src/agents/student.py`
- Test: `tests/test_student.py`

**Interfaces:**
- Consumes: `src.llm.call_structured` (Task 1), `src.memory.classroom_state.StudentMemory` (Task 2)
- Produces: `src.agents.student.react_to_content(student_id: str, persona: dict, memory: StudentMemory, content: dict, violation_notes: list | None = None) -> dict` — `{"answers": [{"question": str, "given_answer": str}], "reaction_text": str, "updated_memory": {...}}`. Ne reçoit QUE `question` et `concept` de chaque exercice (jamais `expected_answer`, sinon l'élève-agent trivialise la réponse).

- [ ] **Step 1: Écrire le test dans `tests/test_student.py`**

```python
from unittest.mock import patch

from src.agents.student import react_to_content
from src.memory.classroom_state import StudentMemory


def test_react_to_content_returns_structured_reaction_and_hides_expected_answer():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": ["confond a et b"]}
    memory = StudentMemory(profile="rapide", mastered_concepts=["variables"])
    content = {"lesson": "les boucles for", "exercises": [{"question": "q1", "expected_answer": "SECRET", "concept": "boucle for"}]}
    fake_result = {
        "answers": [{"question": "q1", "given_answer": "ma réponse"}],
        "reaction_text": "facile",
        "updated_memory": {
            "profile": "rapide", "mastered_concepts": ["variables", "boucle for"],
            "shaky_concepts": [], "forgotten_concepts": [], "engagement_trend": [0.9],
            "history_notes": "a bien suivi",
        },
    }
    with patch("src.agents.student.call_structured", return_value=fake_result) as mock_call:
        result = react_to_content("e1", persona, memory, content)
    assert result == fake_result
    system_arg, user_arg = mock_call.call_args[0][:2]
    assert "confond a et b" in system_arg
    assert "les boucles for" not in user_arg or "q1" in user_arg
    assert "SECRET" not in user_arg
    assert mock_call.call_args.kwargs.get("cacheable_system") is True


def test_react_to_content_includes_violation_notes_when_retrying():
    persona = {"id": "e1", "profile": "rapide", "misconceptions": []}
    memory = StudentMemory(profile="rapide")
    content = {"lesson": "l", "exercises": [{"question": "q1", "expected_answer": "a", "concept": "c"}]}
    fake_result = {"answers": [], "reaction_text": "x", "updated_memory": {
        "profile": "rapide", "mastered_concepts": [], "shaky_concepts": [],
        "forgotten_concepts": [], "engagement_trend": [], "history_notes": "",
    }}
    with patch("src.agents.student.call_structured", return_value=fake_result) as mock_call:
        react_to_content("e1", persona, memory, content, violation_notes=["concept jamais enseigné"])
    _, user_arg = mock_call.call_args[0][:2]
    assert "concept jamais enseigné" in user_arg
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_student.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents.student'`

- [ ] **Step 3: Implémenter `src/agents/student.py`**

```python
from src.llm import call_structured

STUDENT_TOOL_NAME = "submit_reaction"
STUDENT_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "given_answer": {"type": "string"},
                },
                "required": ["question", "given_answer"],
            },
        },
        "reaction_text": {"type": "string"},
        "updated_memory": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "mastered_concepts": {"type": "array", "items": {"type": "string"}},
                "shaky_concepts": {"type": "array", "items": {"type": "string"}},
                "forgotten_concepts": {"type": "array", "items": {"type": "string"}},
                "engagement_trend": {"type": "array", "items": {"type": "number"}},
                "history_notes": {"type": "string"},
            },
            "required": [
                "profile", "mastered_concepts", "shaky_concepts",
                "forgotten_concepts", "engagement_trend", "history_notes",
            ],
        },
    },
    "required": ["answers", "reaction_text", "updated_memory"],
}

STUDENT_SYSTEM_TEMPLATE = (
    'Tu es un élève simulé nommé {student_id}, de profil "{profile}".\n'
    "Méprises caractéristiques de ce profil : {misconceptions}.\n"
    "Tu reçois un contenu de cours et ta propre mémoire (ce que tu maîtrises, ce qui est fragile, "
    "ce que tu as oublié). Réponds à chaque exercice en restant cohérent avec tes méprises si elles "
    "s'appliquent encore, sauf si le cours vient de les corriger clairement. Décide toi-même, selon "
    'ta persona et ta mémoire, ce que tu retiens, oublies ou consolides dans "updated_memory".'
)


def react_to_content(student_id: str, persona: dict, memory, content: dict, violation_notes=None) -> dict:
    misconceptions = ", ".join(persona.get("misconceptions", [])) or "aucune en particulier"
    system = STUDENT_SYSTEM_TEMPLATE.format(
        student_id=student_id, profile=persona["profile"], misconceptions=misconceptions
    )
    visible_exercises = [{"question": e["question"], "concept": e["concept"]} for e in content["exercises"]]
    user_prompt = (
        f"Ta mémoire actuelle : {memory.to_dict()}\n"
        f"Leçon : {content['lesson']}\n"
        f"Exercices : {visible_exercises}\n"
    )
    if violation_notes:
        user_prompt += (
            f"\nTa précédente réponse a été jugée invraisemblable pour les raisons suivantes : "
            f"{violation_notes}. Corrige ta réponse en conséquence.\n"
        )
    return call_structured(system, user_prompt, STUDENT_TOOL_NAME, STUDENT_SCHEMA, cacheable_system=True)
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_student.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/student.py tests/test_student.py
git commit -m "feat: student agent answers exercises, hides expected answers, supports retry"
```

---

### Task 5: Agents Diagnostician (correction + taux de réussite) et Reviser

**Files:**
- Create: `src/agents/diagnostician.py`, `src/agents/reviser.py`
- Test: `tests/test_diagnostician.py`, `tests/test_reviser.py`

**Interfaces:**
- Consumes: `src.llm.call_structured` (Task 1)
- Produces: `src.agents.diagnostician.diagnose(reactions: dict, exercises: list) -> dict` — `{"collective_confusion": list, "boredom_level": float, "dropout_risk_students": list, "fragile_concepts": list, "needs_revision": bool, "summary": str, "success_rate_by_concept": dict[str, float], "graded_answers": [{"student_id": str, "question": str, "correct": bool}]}`
- Produces: `src.agents.reviser.revise_instructions(diagnosis: dict, content: dict) -> str`

- [ ] **Step 1: Écrire le test dans `tests/test_diagnostician.py`**

```python
from unittest.mock import patch

from src.agents.diagnostician import diagnose


def test_diagnose_passes_exercises_and_reactions_returns_health_report():
    reactions = {"e1": {"answers": [{"question": "q", "given_answer": "faux"}], "reaction_text": "perdu"}}
    exercises = [{"question": "q", "expected_answer": "vrai", "concept": "boucle for"}]
    fake_result = {
        "collective_confusion": ["boucle for"],
        "boredom_level": 0.2,
        "dropout_risk_students": ["e1"],
        "fragile_concepts": ["boucle for"],
        "needs_revision": True,
        "summary": "e1 est perdu sur les boucles",
        "success_rate_by_concept": {"boucle for": 0.0},
        "graded_answers": [{"student_id": "e1", "question": "q", "correct": False}],
    }
    with patch("src.agents.diagnostician.call_structured", return_value=fake_result) as mock_call:
        result = diagnose(reactions, exercises)
    assert result == fake_result
    _, user_arg = mock_call.call_args[0][:2]
    assert "e1" in user_arg
    assert "vrai" in user_arg
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_diagnostician.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents.diagnostician'`

- [ ] **Step 3: Implémenter `src/agents/diagnostician.py`**

```python
from src.llm import call_structured

DIAGNOSTICIAN_TOOL_NAME = "submit_diagnosis"
DIAGNOSTICIAN_SCHEMA = {
    "type": "object",
    "properties": {
        "collective_confusion": {"type": "array", "items": {"type": "string"}},
        "boredom_level": {"type": "number"},
        "dropout_risk_students": {"type": "array", "items": {"type": "string"}},
        "fragile_concepts": {"type": "array", "items": {"type": "string"}},
        "needs_revision": {"type": "boolean"},
        "summary": {"type": "string"},
        "success_rate_by_concept": {"type": "object", "additionalProperties": {"type": "number"}},
        "graded_answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string"},
                    "question": {"type": "string"},
                    "correct": {"type": "boolean"},
                },
                "required": ["student_id", "question", "correct"],
            },
        },
    },
    "required": [
        "collective_confusion", "boredom_level", "dropout_risk_students", "fragile_concepts",
        "needs_revision", "summary", "success_rate_by_concept", "graded_answers",
    ],
}

DIAGNOSTICIAN_SYSTEM = (
    "Tu es Diagnostician. Tu reçois les réponses des élèves aux exercices ainsi que les réponses "
    "attendues, et leurs réactions. Corrige chaque réponse (correct/incorrect) en comparant "
    "given_answer à expected_answer (accepte les formulations équivalentes). Calcule un taux de "
    "réussite par concept (fraction de réponses correctes parmi les réponses concernant ce concept). "
    "Puis résume l'état qualitatif de la classe."
)


def diagnose(reactions: dict, exercises: list) -> dict:
    user_prompt = (
        f"Exercices avec réponse attendue : {exercises}\n"
        f"Réponses et réactions des élèves : {reactions}"
    )
    return call_structured(DIAGNOSTICIAN_SYSTEM, user_prompt, DIAGNOSTICIAN_TOOL_NAME, DIAGNOSTICIAN_SCHEMA)
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_diagnostician.py -v`
Expected: PASS

- [ ] **Step 5: Écrire le test dans `tests/test_reviser.py`**

```python
from unittest.mock import patch

from src.agents.reviser import revise_instructions


def test_revise_instructions_returns_notes_string():
    diagnosis = {"summary": "e1 est perdu", "needs_revision": True}
    content = {"lesson": "texte", "exercises": []}
    fake_result = {"revision_notes": "simplifier l'exemple 2"}
    with patch("src.agents.reviser.call_structured", return_value=fake_result) as mock_call:
        result = revise_instructions(diagnosis, content)
    assert result == "simplifier l'exemple 2"
    assert "e1 est perdu" in mock_call.call_args[0][1]
```

- [ ] **Step 6: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_reviser.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents.reviser'`

- [ ] **Step 7: Implémenter `src/agents/reviser.py`**

```python
from src.llm import call_structured

REVISER_TOOL_NAME = "submit_revision_notes"
REVISER_SCHEMA = {
    "type": "object",
    "properties": {"revision_notes": {"type": "string"}},
    "required": ["revision_notes"],
}

REVISER_SYSTEM = (
    "Tu es Reviser, un agent qui traduit un diagnostic de classe en instructions concrètes et "
    "actionnables de révision pour l'agent qui génère le contenu."
)


def revise_instructions(diagnosis: dict, content: dict) -> str:
    user_prompt = (
        f"Diagnostic de la classe : {diagnosis}\n"
        f"Contenu actuel :\nLeçon : {content['lesson']}\nExercices : {content['exercises']}\n"
    )
    result = call_structured(REVISER_SYSTEM, user_prompt, REVISER_TOOL_NAME, REVISER_SCHEMA)
    return result["revision_notes"]
```

- [ ] **Step 8: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_reviser.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/agents/diagnostician.py src/agents/reviser.py tests/test_diagnostician.py tests/test_reviser.py
git commit -m "feat: diagnostician grades answers and computes success rate; reviser agent"
```

---

### Task 6: DriftWatcher déterministe (validate_reaction, clamp_reaction, check_drift)

**Files:**
- Create: `src/agents/drift_watcher.py`
- Test: `tests/test_drift_watcher.py`

**Interfaces:**
- Consumes: `src.memory.classroom_state.StudentMemory` (Task 2)
- Produces: `src.agents.drift_watcher.validate_reaction(reaction: dict, previous_memory: StudentMemory, taught_concepts: set) -> tuple[bool, list[str]]`
- Produces: `src.agents.drift_watcher.clamp_reaction(reaction: dict, previous_memory: StudentMemory, taught_concepts: set) -> dict`
- Produces: `src.agents.drift_watcher.check_drift(diagnosis_history: list[dict]) -> list[str]`

- [ ] **Step 1: Écrire les tests dans `tests/test_drift_watcher.py`**

```python
from src.agents.drift_watcher import check_drift, clamp_reaction, validate_reaction
from src.memory.classroom_state import StudentMemory


def make_reaction(mastered=None, forgotten=None, engagement=None):
    return {
        "answers": [], "reaction_text": "",
        "updated_memory": {
            "profile": "rapide",
            "mastered_concepts": mastered or [],
            "shaky_concepts": [],
            "forgotten_concepts": forgotten or [],
            "engagement_trend": engagement or [],
            "history_notes": "",
        },
    }


def test_validate_reaction_rejects_mastery_of_untaught_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(mastered=["boucle for"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts=set())
    assert is_valid is False
    assert any("jamais enseigné" in r for r in reasons)


def test_validate_reaction_accepts_mastery_of_taught_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(mastered=["boucle for"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"boucle for"})
    assert is_valid is True
    assert reasons == []


def test_validate_reaction_rejects_forgetting_never_known_concept():
    prev = StudentMemory(profile="rapide")
    reaction = make_reaction(forgotten=["variables"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"variables"})
    assert is_valid is False
    assert any("n'était pas acquis" in r for r in reasons)


def test_validate_reaction_accepts_forgetting_previously_mastered_concept():
    prev = StudentMemory(profile="rapide", mastered_concepts=["variables"])
    reaction = make_reaction(forgotten=["variables"])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts={"variables"})
    assert is_valid is True


def test_validate_reaction_rejects_large_engagement_jump():
    prev = StudentMemory(profile="rapide", engagement_trend=[0.2])
    reaction = make_reaction(engagement=[0.9])
    is_valid, reasons = validate_reaction(reaction, prev, taught_concepts=set())
    assert is_valid is False
    assert any("Engagement" in r for r in reasons)


def test_clamp_reaction_removes_illegitimate_mastery_and_clamps_engagement():
    prev = StudentMemory(profile="rapide", engagement_trend=[0.2])
    reaction = make_reaction(mastered=["x", "boucle for"], engagement=[0.9])
    clamped = clamp_reaction(reaction, prev, taught_concepts={"boucle for"})
    assert clamped["updated_memory"]["mastered_concepts"] == ["boucle for"]
    assert clamped["updated_memory"]["engagement_trend"] == [0.6]


def test_check_drift_empty_history():
    assert check_drift([]) == []


def test_check_drift_stagnation():
    d = {"needs_revision": True, "summary": "toujours perdu", "boredom_level": 0.3, "fragile_concepts": ["x"], "collective_confusion": ["x"]}
    flags = check_drift([d, dict(d)])
    assert any("stagnation" in f.lower() for f in flags)


def test_check_drift_perfect_class_flagged():
    d = {"needs_revision": False, "summary": "tout va bien", "boredom_level": 0.0, "fragile_concepts": [], "collective_confusion": []}
    flags = check_drift([d, dict(d)])
    assert len(flags) >= 1
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_drift_watcher.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.agents.drift_watcher'`

- [ ] **Step 3: Implémenter `src/agents/drift_watcher.py`**

```python
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
            clamped_value = prev_eng + (0.4 if new_eng > prev_eng else -0.4)
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_drift_watcher.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agents/drift_watcher.py tests/test_drift_watcher.py
git commit -m "feat: deterministic drift watcher (validate, clamp, check_drift)"
```

---

### Task 7: Orchestrateur (parallélisation, DriftWatcher intégré, snapshots, validation humaine) + CLI

**Files:**
- Create: `src/orchestrator.py`, `main.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: tous les agents (Tasks 3-6), `ClassroomState` (Task 2), `src.config.N_SESSIONS`, `src.config.MAX_ITER`, `src.fake_agents.*` (Task 2)
- Produces: `src.orchestrator.summarize_classroom(state: ClassroomState) -> str`
- Produces: `src.orchestrator.run(objective: str, personas: list[dict], planner=plan_sessions, generator=generate_content, student_react=react_to_content, diagnostician=diagnose, reviser=revise_instructions, drift_check=check_drift, n_sessions: int = N_SESSIONS, max_iter: int = MAX_ITER, session_plan_hook=None) -> dict` — `run_log` avec `run_id`, `objective`, `sessions` (liste de `{spec, iterations, final_content, memory_snapshot}`), `final_classroom_state`. Chaque itération de `session["iterations"]` a les clés `iteration, content, reactions, diagnosis, drift_corrections, run_drift_flags, revision_notes_used`.
- Produces: `main.py` — CLI `python main.py --objective "..." [--fake] [--auto-approve]`

- [ ] **Step 1: Écrire les tests dans `tests/test_orchestrator.py`**

```python
from src.orchestrator import run


def fake_planner(objective, n_sessions):
    return [{"title": f"Séance {i + 1}", "focus": "c1", "goal": "g"} for i in range(n_sessions)]


def fake_generator(session_spec, classroom_summary, revision_notes):
    return {
        "lesson": f"contenu ({revision_notes})",
        "exercises": [{"question": "q", "expected_answer": "a", "concept": "c1"}],
    }


def make_fake_student_react():
    def fake_student_react(student_id, persona, memory, content, violation_notes=None):
        return {
            "answers": [{"question": "q", "given_answer": "a"}],
            "reaction_text": "ok",
            "updated_memory": {
                "profile": persona["profile"],
                "mastered_concepts": ["c1"],
                "shaky_concepts": [],
                "forgotten_concepts": [],
                "engagement_trend": [0.8],
                "history_notes": "ok",
            },
        }
    return fake_student_react


def make_fake_diagnostician(needs_revision_sequence):
    calls = {"n": 0}

    def fake_diagnostician(reactions, exercises):
        idx = min(calls["n"], len(needs_revision_sequence) - 1)
        needs_revision = needs_revision_sequence[idx]
        calls["n"] += 1
        return {
            "collective_confusion": [], "boredom_level": 0.1, "dropout_risk_students": [],
            "fragile_concepts": [], "needs_revision": needs_revision, "summary": f"état {idx}",
            "success_rate_by_concept": {"c1": 1.0},
            "graded_answers": [{"student_id": sid, "question": "q", "correct": True} for sid in reactions],
        }
    return fake_diagnostician


def fake_reviser(diagnosis, content):
    return "simplifier"


def fake_drift_check(history):
    return []


def test_run_stops_reviser_loop_when_needs_revision_false():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([True, False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=2,
    )
    session = run_log["sessions"][0]
    assert len(session["iterations"]) == 2
    assert session["iterations"][0]["revision_notes_used"] is None
    assert session["iterations"][1]["revision_notes_used"] == "simplifier"


def test_run_stops_at_max_iter():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([True, True, True]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=1,
    )
    assert len(run_log["sessions"][0]["iterations"]) == 2


def test_run_updates_classroom_memory_and_snapshot():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]
    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=2,
    )
    assert run_log["final_classroom_state"]["e1"]["mastered_concepts"] == ["c1"]
    assert run_log["sessions"][0]["memory_snapshot"]["e1"]["mastered_concepts"] == ["c1"]


def test_run_clamps_implausible_mastery_via_drift_watcher():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]

    def student_claims_untaught_mastery(student_id, persona, memory, content, violation_notes=None):
        return {
            "answers": [{"question": "q", "given_answer": "a"}],
            "reaction_text": "ok",
            "updated_memory": {
                "profile": persona["profile"],
                "mastered_concepts": ["concept_jamais_enseigne"],
                "shaky_concepts": [], "forgotten_concepts": [], "engagement_trend": [], "history_notes": "",
            },
        }

    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=student_claims_untaught_mastery,
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=0,
    )
    corrections = run_log["sessions"][0]["iterations"][0]["drift_corrections"]
    assert "e1" in corrections
    assert run_log["final_classroom_state"]["e1"]["mastered_concepts"] == []


def test_session_plan_hook_can_edit_sessions():
    personas = [{"id": "e1", "profile": "rapide", "misconceptions": []}]

    def hook(sessions):
        return [{**sessions[0], "title": "Titre édité"}]

    run_log = run(
        "objectif test", personas,
        planner=fake_planner, generator=fake_generator, student_react=make_fake_student_react(),
        diagnostician=make_fake_diagnostician([False]), reviser=fake_reviser,
        drift_check=fake_drift_check, n_sessions=1, max_iter=0, session_plan_hook=hook,
    )
    assert run_log["sessions"][0]["spec"]["title"] == "Titre édité"
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.orchestrator'`

- [ ] **Step 3: Implémenter `src/orchestrator.py`**

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Implémenter `main.py`**

```python
import argparse
import json
import os

from dotenv import load_dotenv

from src.orchestrator import run


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

    from src.report import save_report

    run_dir = f"data/runs/{run_log['run_id']}"
    os.makedirs(run_dir, exist_ok=True)
    with open(f"{run_dir}/run_log.json", "w", encoding="utf-8") as f:
        json.dump(run_log, f, ensure_ascii=False, indent=2)
    save_report(run_log, f"{run_dir}/report.md")
    print(f"Run terminé : {run_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Vérifier la syntaxe de `main.py`**

Run: `python -c "import ast; ast.parse(open('main.py').read())"`
Expected: pas d'erreur

- [ ] **Step 7: Commit**

```bash
git add src/orchestrator.py main.py tests/test_orchestrator.py
git commit -m "feat: orchestrator with parallel students, drift integration, human plan validation, CLI"
```

---

### Task 8: Rapport Markdown et smoke test end-to-end

**Files:**
- Create: `src/report.py`
- Test: `tests/test_report.py`
- Create: `docs/smoke-test-notes.md`

**Interfaces:**
- Consumes: `run_log` dict produit par `src.orchestrator.run` (Task 7)
- Produces: `src.report.render_report(run_log: dict) -> str`, `src.report.save_report(run_log: dict, path: str) -> None`

- [ ] **Step 1: Écrire le test dans `tests/test_report.py`**

```python
from src.report import render_report, save_report


def make_fake_run_log():
    return {
        "run_id": "test-run",
        "objective": "apprendre les boucles",
        "sessions": [
            {
                "spec": {"title": "Séance 1", "focus": "bases", "goal": "comprendre for"},
                "iterations": [
                    {
                        "iteration": 0,
                        "content": {"lesson": "leçon v1", "exercises": [{"question": "q", "expected_answer": "a", "concept": "for"}]},
                        "diagnosis": {"summary": "confusion sur for", "success_rate_by_concept": {"for": 0.3}},
                        "drift_corrections": {},
                        "run_drift_flags": [],
                        "revision_notes_used": None,
                    },
                    {
                        "iteration": 1,
                        "content": {"lesson": "leçon v2", "exercises": [{"question": "q", "expected_answer": "a", "concept": "for"}]},
                        "diagnosis": {"summary": "ça va mieux", "success_rate_by_concept": {"for": 0.9}},
                        "drift_corrections": {"e1": ["Concept 'x' marqué maîtrisé mais jamais enseigné."]},
                        "run_drift_flags": ["Classe parfaite sans aucune friction — signal potentiellement irréaliste."],
                        "revision_notes_used": "simplifier",
                    },
                ],
                "final_content": {"lesson": "leçon v2", "exercises": []},
                "memory_snapshot": {"e1": {"profile": "rapide", "mastered_concepts": ["for"], "shaky_concepts": [], "forgotten_concepts": []}},
            }
        ],
        "final_classroom_state": {
            "e1": {"profile": "rapide", "mastered_concepts": ["for"], "shaky_concepts": [], "forgotten_concepts": []}
        },
    }


def test_render_report_contains_key_sections():
    report = render_report(make_fake_run_log())
    assert "apprendre les boucles" in report
    assert "Séance 1" in report
    assert "leçon v1" in report
    assert "leçon v2" in report
    assert "30%" in report
    assert "90%" in report
    assert "simplifier" in report
    assert "Classe parfaite" in report
    assert "marqué maîtrisé mais jamais enseigné" in report
    assert "e1" in report


def test_save_report_writes_file(tmp_path):
    path = tmp_path / "sub" / "report.md"
    save_report(make_fake_run_log(), str(path))
    assert path.exists()
    assert "apprendre les boucles" in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'src.report'`

- [ ] **Step 3: Implémenter `src/report.py`**

```python
import os


def render_report(run_log: dict) -> str:
    lines = [f"# Rapport de run — {run_log['run_id']}", "", f"**Objectif :** {run_log['objective']}", ""]

    for i, session in enumerate(run_log["sessions"], start=1):
        spec = session["spec"]
        lines.append(f"## Séance {i} — {spec['title']}")
        lines.append(f"*Objectif : {spec['goal']}*")
        lines.append("")
        for it in session["iterations"]:
            lines.append(f"### Itération {it['iteration']}")
            lines.append(f"**Contenu proposé :**\n\n{it['content']['lesson']}")
            lines.append("")
            lines.append(f"**Diagnostic :** {it['diagnosis']['summary']}")
            lines.append("")
            lines.append("**Taux de réussite par concept :**")
            for concept, rate in it["diagnosis"]["success_rate_by_concept"].items():
                lines.append(f"- {concept} : {rate:.0%}")
            if it["drift_corrections"]:
                lines.append("")
                lines.append(f"**Corrections DriftWatcher appliquées :** {it['drift_corrections']}")
            if it["run_drift_flags"]:
                lines.append(f"**Anomalies de trajectoire signalées :** {', '.join(it['run_drift_flags'])}")
            if it["revision_notes_used"]:
                lines.append(f"**Notes de révision appliquées :** {it['revision_notes_used']}")
            lines.append("")
        lines.append(f"**Contenu final retenu :**\n\n{session['final_content']['lesson']}")
        lines.append("")
        lines.append("**Mémoire des élèves après cette séance :**")
        for sid, mem in session["memory_snapshot"].items():
            lines.append(
                f"- **{sid}** : maîtrisé={mem['mastered_concepts']}, "
                f"fragile={mem['shaky_concepts']}, oublié={mem['forgotten_concepts']}"
            )
        lines.append("")

    lines.append("## Trajectoire mémoire finale")
    for sid, mem in run_log["final_classroom_state"].items():
        lines.append(
            f"- **{sid}** ({mem['profile']}) : maîtrisé={mem['mastered_concepts']}, "
            f"fragile={mem['shaky_concepts']}, oublié={mem['forgotten_concepts']}"
        )
    return "\n".join(lines)


def save_report(run_log: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_report(run_log))
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lancer toute la suite pour confirmer que rien n'est cassé**

Run: `python -m pytest -v`
Expected: PASS (tous les tests des tâches 1 à 8)

- [ ] **Step 6: Smoke test hors-ligne (rapide, sans clé API)**

Run: `python main.py --objective "faire comprendre les boucles for/while à des débutants" --fake --auto-approve`
Expected: se termine en quelques secondes, affiche `Run terminé : data/runs/<run_id>`

- [ ] **Step 7: Smoke test réel (appel LLM réel)**

Action manuelle : copier `.env.example` vers `.env`, renseigner `ANTHROPIC_API_KEY`, puis :

Run: `pip install -r requirements-dev.txt && python main.py --objective "faire comprendre les boucles for/while à des débutants en programmation, niveau lycée"`
Expected: le plan de séances s'affiche, demande confirmation ; après validation, le run se termine et affiche `Run terminé : data/runs/<run_id>`

- [ ] **Step 8: Vérifier les critères de `docs/architecture.md` et documenter dans `docs/smoke-test-notes.md`**

Contenu attendu du fichier : objectif utilisé, `run_id`, nombre d'itérations par séance, extrait de `success_rate_by_concept` sur au moins deux séances pour un même concept (preuve de mesure de rétention), toute correction DriftWatcher observée, tout `run_drift_flags` observé.

- [ ] **Step 9: Commit**

```bash
git add src/report.py tests/test_report.py docs/smoke-test-notes.md
git commit -m "feat: markdown report with success-rate curve and drift table; document smoke test"
```
