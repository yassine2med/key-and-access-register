"""Command line entry: python -m keyregister status|overdue|holder|check|issue|return."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .register import (RegisterError, check, held_by, issue_key, load_keys, load_log, no_due_date, overdue,
                       return_key, save_log, status)


def _when(text: str | None) -> date:
    return date.fromisoformat(text) if text else date.today()


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 when the report found overdue keys or problems, 2 on bad input."""
    parser = argparse.ArgumentParser(prog="keyregister", description="Key issue register with overdue returns")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("status", "copies out and available per key"), ("overdue", "keys past their due date"),
                       ("check", "find mistakes in the log")):
        p = sub.add_parser(name, help=text)
        p.add_argument("keys")
        p.add_argument("log")
        if name == "overdue":
            p.add_argument("--today", help="YYYY-MM-DD (default: today)")
    h = sub.add_parser("holder", help="keys held by a person or company")
    h.add_argument("log")
    h.add_argument("name")
    i = sub.add_parser("issue", help="give out the next free copy and record it")
    i.add_argument("keys")
    i.add_argument("log")
    i.add_argument("key_id")
    i.add_argument("holder")
    i.add_argument("--on", help="issue date (default: today)")
    i.add_argument("--due", help="due back date")
    r = sub.add_parser("return", help="record a returned key")
    r.add_argument("log")
    r.add_argument("key_id")
    r.add_argument("copy", type=int)
    r.add_argument("--on", help="return date (default: today)")
    args = parser.parse_args(argv)

    try:
        if args.command == "holder":
            rows = held_by(load_log(args.log), args.name)
            for x in rows:
                print(f"{x.key_id} copy {x.copy}  {x.holder}  since {x.issued}")
            print(f"{len(rows)} key(s) held")
            return 0
        if args.command == "return":
            log = load_log(args.log)
            done = return_key(log, args.key_id, args.copy, _when(args.on))
            save_log(args.log, log)
            print(f"{done.key_id} copy {done.copy} returned by {done.holder} on {done.returned}")
            return 0
        keys = load_keys(args.keys)
        log = load_log(args.log)
        if args.command == "status":
            print(f"{'key':<10}{'description':<24}{'copies':>7}{'out':>5}{'free':>6}")
            for row in status(keys, log):
                print(f"{row['key_id']:<10}{row['description']:<24}{row['copies']:>7}{row['out']:>5}{row['available']:>6}")
            return 0
        if args.command == "overdue":
            today = _when(args.today)
            late = overdue(log, today)
            for entry, days in late:
                print(f"{entry.key_id} copy {entry.copy}  {entry.holder:<22} due {entry.due_back}  {days} day(s) late")
            open_ended = no_due_date(log)
            print(f"{len(late)} overdue as of {today}; {len(open_ended)} out with no due date")
            return 1 if late else 0
        if args.command == "check":
            problems = check(keys, log)
            for p in problems:
                print(p)
            print(f"{len(problems)} problem(s)" if problems else "log is consistent")
            return 1 if problems else 0
        new = issue_key(keys, log, args.key_id, args.holder, _when(args.on), date.fromisoformat(args.due) if args.due else None)
        save_log(args.log, log)
        print(f"{new.key_id} copy {new.copy} issued to {new.holder} on {new.issued}")
        return 0
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
        return 2
    except (RegisterError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
