import shutil
from datetime import date
from pathlib import Path

import pytest

from keyregister.__main__ import main
from keyregister.register import (Issue, Key, RegisterError, check, held_by, issue_key, load_keys, load_log,
                                  no_due_date, overdue, return_key, save_log, status)

EX = Path(__file__).resolve().parent.parent / "examples"
TODAY = date(2026, 11, 20)


@pytest.fixture
def keys():
    return load_keys(str(EX / "keys.csv"))


@pytest.fixture
def log():
    return load_log(str(EX / "issues.csv"))


def test_load_counts(keys, log):
    assert len(keys) == 8 and len(log) == 15


def test_status_counts(keys, log):
    rows = {r["key_id"]: r for r in status(keys, log)}
    assert rows["MK-001"]["available"] == 0
    assert rows["GR-GATE"]["out"] == 3 and rows["GR-GATE"]["available"] == 1


def test_returned_copy_is_available(keys, log):
    assert {r["key_id"]: r for r in status(keys, log)}["RM-ELEC"]["out"] == 1


def test_overdue_worst_first(log):
    late = overdue(log, TODAY)
    assert [(i.key_id, d) for i, d in late] == [("K-201", 11), ("RF-HATCH", 10), ("RM-MECH", 6)]


def test_due_today_is_not_overdue(log):
    assert all(i.key_id != "RM-ELEC" for i, _ in overdue(log, TODAY))


def test_returned_never_overdue(log):
    assert all(i.is_out for i, _ in overdue(log, date(2027, 1, 1)))


def test_no_due_date_listed(log):
    assert len(no_due_date(log)) == 9


def test_held_by_is_case_insensitive(log):
    assert len(held_by(log, "CONTRACTOR")) == 3


def test_check_clean_sample(keys, log):
    assert check(keys, log) == []


def test_check_finds_problems(keys):
    bad = [Issue("NOPE", 1, "A", date(2026, 1, 1), None, None),
           Issue("K-101", 9, "A", date(2026, 1, 1), None, None),
           Issue("K-102", 1, "A", date(2026, 3, 1), None, date(2026, 2, 1)),
           Issue("K-201", 1, "A", date(2026, 3, 1), None, None),
           Issue("K-201", 1, "B", date(2026, 3, 2), None, None)]
    text = " | ".join(check(keys, bad))
    assert "not in the key list" in text and "outside 1 to 3" in text
    assert "returned before" in text and "already out" in text


def test_issue_picks_lowest_free_copy(keys, log):
    new = issue_key(keys, log, "K-102", "Tenant", TODAY, date(2026, 11, 27))
    assert new.copy == 2 and len(log) == 16


def test_issue_fails_when_none_free(keys, log):
    with pytest.raises(RegisterError):
        issue_key(keys, log, "RF-HATCH", "Someone", TODAY, None)


def test_issue_rejects_unknown_key_and_bad_due(keys, log):
    with pytest.raises(RegisterError):
        issue_key(keys, log, "ZZ", "A", TODAY, None)
    with pytest.raises(RegisterError):
        issue_key(keys, log, "K-102", "A", TODAY, date(2026, 1, 1))


def test_return_then_reissue_same_copy(keys, log):
    return_key(log, "MK-001", 2, TODAY)
    assert issue_key(keys, log, "MK-001", "New holder", TODAY, None).copy == 2


def test_return_not_out(log):
    with pytest.raises(RegisterError):
        return_key(log, "RM-ELEC", 2, TODAY)


def test_save_and_reload_round_trip(log, tmp_path):
    out = tmp_path / "l.csv"
    save_log(str(out), log)
    again = load_log(str(out))
    assert [(i.key_id, i.copy, i.returned) for i in again] == [(i.key_id, i.copy, i.returned) for i in log]


def test_bad_date_in_file(tmp_path):
    bad = tmp_path / "l.csv"
    bad.write_text("key_id,copy,holder,issued,due_back,returned\nK-101,1,A,yesterday,,\n")
    with pytest.raises(RegisterError):
        load_log(str(bad))


def test_duplicate_key_in_list(tmp_path):
    bad = tmp_path / "k.csv"
    bad.write_text("key_id,description,area,copies\nA,x,y,1\nA,x,y,1\n")
    with pytest.raises(RegisterError):
        load_keys(str(bad))


def test_cli_flow(tmp_path, capsys):
    log = tmp_path / "log.csv"
    shutil.copy(EX / "issues.csv", log)
    keys = str(EX / "keys.csv")
    assert main(["overdue", keys, str(log), "--today", "2026-11-20"]) == 1
    assert main(["return", str(log), "K-201", "2", "--on", "2026-11-20"]) == 0
    assert main(["overdue", keys, str(log), "--today", "2026-11-09"]) == 0
    assert main(["issue", keys, str(log), "K-102", "Tenant", "--on", "2026-11-20"]) == 0
    assert main(["issue", keys, str(log), "K-102", "Tenant", "--on", "2026-11-20"]) == 2
    assert main(["status", keys, str(log)]) == 0
    assert main(["check", keys, str(log)]) == 0
    assert main(["holder", str(log), "tenant"]) == 0
    assert main(["status", keys, str(tmp_path / "none.csv")]) == 2
