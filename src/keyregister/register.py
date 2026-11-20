"""Key register: who holds which key copy, what is overdue, and issue and return updates."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date

LOG_FIELDS = ["key_id", "copy", "holder", "issued", "due_back", "returned"]


class RegisterError(ValueError):
    pass


@dataclass
class Key:
    key_id: str
    description: str
    area: str
    copies: int


@dataclass
class Issue:
    key_id: str
    copy: int
    holder: str
    issued: date
    due_back: date | None
    returned: date | None

    @property
    def is_out(self) -> bool:
        return self.returned is None


def _date(value: str, where: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegisterError(f"{where}: {value!r} is not a YYYY-MM-DD date") from exc


def load_keys(path: str) -> dict[str, Key]:
    keys: dict[str, Key] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for n, row in enumerate(csv.DictReader(handle), start=2):
            try:
                copies = int(row["copies"])
            except (KeyError, ValueError, TypeError) as exc:
                raise RegisterError(f"{path} line {n}: copies must be a whole number") from exc
            key_id = (row.get("key_id") or "").strip()
            if not key_id:
                raise RegisterError(f"{path} line {n}: key_id is empty")
            if key_id in keys:
                raise RegisterError(f"{path} line {n}: key {key_id} is listed twice")
            keys[key_id] = Key(key_id, row.get("description", "").strip(), row.get("area", "").strip(), copies)
    return keys


def load_log(path: str) -> list[Issue]:
    issues = []
    with open(path, newline="", encoding="utf-8") as handle:
        for n, row in enumerate(csv.DictReader(handle), start=2):
            where = f"{path} line {n}"
            try:
                copy = int(row["copy"])
            except (KeyError, ValueError, TypeError) as exc:
                raise RegisterError(f"{where}: copy must be a whole number") from exc
            issued = _date(row.get("issued", ""), where)
            if issued is None:
                raise RegisterError(f"{where}: issued date is required")
            issues.append(Issue(row["key_id"].strip(), copy, row["holder"].strip(), issued,
                                _date(row.get("due_back", ""), where), _date(row.get("returned", ""), where)))
    return issues


def save_log(path: str, issues: list[Issue]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(LOG_FIELDS)
        for i in issues:
            writer.writerow([i.key_id, i.copy, i.holder, i.issued.isoformat(),
                             i.due_back.isoformat() if i.due_back else "",
                             i.returned.isoformat() if i.returned else ""])


def status(keys: dict[str, Key], issues: list[Issue]) -> list[dict]:
    rows = []
    for key in keys.values():
        out = [i for i in issues if i.key_id == key.key_id and i.is_out]
        rows.append({"key_id": key.key_id, "description": key.description, "copies": key.copies,
                     "out": len(out), "available": key.copies - len(out)})
    return rows


def overdue(issues: list[Issue], today: date) -> list[tuple[Issue, int]]:
    """Open issues past their due date, with days late, worst first."""
    late = [(i, (today - i.due_back).days) for i in issues if i.is_out and i.due_back and i.due_back < today]
    return sorted(late, key=lambda pair: (-pair[1], pair[0].key_id, pair[0].copy))


def no_due_date(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.is_out and i.due_back is None]


def held_by(issues: list[Issue], name: str) -> list[Issue]:
    needle = name.lower()
    return [i for i in issues if i.is_out and needle in i.holder.lower()]


def check(keys: dict[str, Key], issues: list[Issue]) -> list[str]:
    """Integrity problems in the log."""
    problems = []
    open_copies: set[tuple[str, int]] = set()
    for n, i in enumerate(issues, start=1):
        label = f"log row {n} ({i.key_id} copy {i.copy})"
        key = keys.get(i.key_id)
        if key is None:
            problems.append(f"{label}: key is not in the key list")
            continue
        if not 1 <= i.copy <= key.copies:
            problems.append(f"{label}: copy number is outside 1 to {key.copies}")
        if i.returned and i.returned < i.issued:
            problems.append(f"{label}: returned before it was issued")
        if i.due_back and i.due_back < i.issued:
            problems.append(f"{label}: due date is before the issue date")
        if i.is_out:
            if (i.key_id, i.copy) in open_copies:
                problems.append(f"{label}: this copy is already out to someone else")
            open_copies.add((i.key_id, i.copy))
    return problems


def issue_key(keys: dict[str, Key], issues: list[Issue], key_id: str, holder: str, on: date,
              due: date | None) -> Issue:
    """Give out the lowest free copy. Raises RegisterError when none is free."""
    key = keys.get(key_id)
    if key is None:
        raise RegisterError(f"unknown key {key_id}")
    if not holder.strip():
        raise RegisterError("holder is required")
    if due and due < on:
        raise RegisterError("due date is before the issue date")
    taken = {i.copy for i in issues if i.key_id == key_id and i.is_out}
    free = [c for c in range(1, key.copies + 1) if c not in taken]
    if not free:
        raise RegisterError(f"all {key.copies} copies of {key_id} are out")
    new = Issue(key_id, free[0], holder.strip(), on, due, None)
    issues.append(new)
    return new


def return_key(issues: list[Issue], key_id: str, copy: int, on: date) -> Issue:
    for i in issues:
        if i.key_id == key_id and i.copy == copy and i.is_out:
            if on < i.issued:
                raise RegisterError("return date is before the issue date")
            i.returned = on
            return i
    raise RegisterError(f"copy {copy} of {key_id} is not out")
