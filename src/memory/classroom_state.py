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
