import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import SUBJECTS_DIR


@dataclass
class Question:
    number: int
    text: str
    options: list[tuple[str, str]] = field(default_factory=list)
    correct: Optional[str] = None


# "1." or "1)" or "12. " at start of line (after optional whitespace/tab)
_Q_RE = re.compile(r"^\s*(\d{1,3})[.)]\s*(.*)$")
# "A)" / "+B)" / "a)" — option letter, optionally prefixed with +
_OPT_RE = re.compile(r"^\s*(\+?)\s*([A-DAa-d])[.)]\s*(.*)$")


def parse_file(path: Path) -> list[Question]:
    """Parse a test file into a list of Question objects.

    Format:
        1. Question text (may span multiple lines)
        A) option
        +B) correct option
        C) option
        D) option
        2. Next question...
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    questions: list[Question] = []
    current: Optional[Question] = None
    state = "idle"  # idle | question_text | options

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        opt_match = _OPT_RE.match(line)
        q_match = _Q_RE.match(line)

        # A new question header looks like "12. ..." — but option lines like "A)"
        # also start with a letter. So we check option first, then question.
        if opt_match and state in ("question_text", "options"):
            plus, letter, opt_text = opt_match.groups()
            letter = letter.upper()
            if current is not None:
                current.options.append((letter, opt_text.strip()))
                if plus == "+":
                    current.correct = letter
            state = "options"
            continue

        if q_match:
            # Could be a new question. Heuristic: only treat as new question if
            # we are not in the middle of a question_text block AND the number
            # is plausible (e.g., next number or close). Simpler: always treat
            # as new question if the previous question already has options OR
            # we are idle.
            if current is None or state == "options" or current.options:
                if current is not None and current.options:
                    questions.append(current)
                num, q_text = q_match.groups()
                current = Question(number=int(num), text=q_text.strip())
                state = "question_text"
                continue

        # Continuation of question text (e.g., code lines)
        if state == "question_text" and current is not None:
            current.text = (current.text + "\n" + stripped).strip()

    if current is not None and current.options:
        questions.append(current)

    # Sanity: keep only questions with exactly 4 options and a correct answer
    cleaned = [q for q in questions if len(q.options) >= 2 and q.correct]
    return cleaned


def list_subjects() -> list[tuple[str, Path]]:
    """Return list of (display_name, path) for every .txt file in subjects/."""
    subjects = []
    for p in sorted(SUBJECTS_DIR.glob("*.txt")):
        name = p.stem.replace("_", " ").replace("-", " ").strip().title()
        subjects.append((name, p))
    return subjects


def load_subject(path: Path) -> list[Question]:
    return parse_file(path)
