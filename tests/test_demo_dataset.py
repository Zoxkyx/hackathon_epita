import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_html_report import build_demo_run_log


def _revised_sessions(run_log):
    return [s for s in run_log["sessions"] if len(s["iterations"]) > 1]


def test_reviser_notes_are_all_distinct():
    notes = [s["iterations"][-1]["revision_notes_used"] for s in _revised_sessions(build_demo_run_log())]
    assert len(notes) == len(set(notes)), f"notes du Reviser dupliquees : {notes}"


def test_lesson_texts_are_all_distinct():
    lessons = []
    for session in build_demo_run_log()["sessions"]:
        for it in session["iterations"]:
            lessons.append(it["content"]["lesson"])
    assert len(lessons) == len(set(lessons)), "textes de lecon dupliques"


def test_lessons_are_not_the_same_sentence_with_one_word_swapped():
    """Deux lecons ne doivent pas partager leur squelette de phrase.

    On compare les lecons debarrassees des noms de concepts : si deux d'entre
    elles deviennent identiques, c'est qu'un seul mot les distinguait.
    """
    run_log = build_demo_run_log()
    concepts = {s["spec"]["focus"] for s in run_log["sessions"]}

    skeletons = []
    for session in run_log["sessions"]:
        for it in session["iterations"]:
            text = it["content"]["lesson"]
            for concept in concepts:
                text = text.replace(concept, "")
            skeletons.append(" ".join(text.split()))

    assert len(skeletons) == len(set(skeletons)), (
        "des lecons partagent le meme gabarit de phrase : "
        f"{[s for s in skeletons if skeletons.count(s) > 1][:2]}"
    )
