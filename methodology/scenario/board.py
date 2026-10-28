"""Shared message board for the research agents (append-only log in research/board.md).

    python3 research/board.py post --from NAME --type TYPE --to ALL "message text"
    python3 research/board.py read [--last N] [--type TYPE] [--from NAME]

TYPE is one of: BROADCAST (finding everyone should know), QUESTION, CHALLENGE, REPLY, DECISION, STATUS.
Posts are appended atomically, so several agents can post at the same time.
"""
import argparse, os, re, sys
from datetime import datetime
from pathlib import Path

BOARD = Path(__file__).resolve().parent / "board.md"
TYPES = ["BROADCAST", "QUESTION", "CHALLENGE", "REPLY", "DECISION", "STATUS"]


def post(a):
    msg = " ".join(a.message).strip() or sys.stdin.read().strip()
    n = len(re.findall(r"^### #", BOARD.read_text(), flags=re.M)) + 1 if BOARD.exists() else 1
    entry = f"\n### #{n} | {datetime.now():%Y-%m-%d %H:%M} | {a.sender} -> {a.to} | {a.type}\n{msg}\n"
    fd = os.open(BOARD, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    os.write(fd, entry.encode())
    os.close(fd)
    print(f"posted #{n}")


def read(a):
    if not BOARD.exists():
        return print("(board is empty)")
    posts = re.split(r"\n(?=### #)", BOARD.read_text())
    posts = [p for p in posts if p.startswith("### #")]
    if a.type:
        posts = [p for p in posts if p.splitlines()[0].endswith(f"| {a.type}")]
    if a.sender:
        posts = [p for p in posts if f"| {a.sender} ->" in p.splitlines()[0]]
    print("\n".join(posts[-a.last:] if a.last else posts))


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("post"); p.add_argument("--from", dest="sender", required=True)
p.add_argument("--type", choices=TYPES, default="BROADCAST"); p.add_argument("--to", default="ALL")
p.add_argument("message", nargs="*"); p.set_defaults(fn=post)
r = sub.add_parser("read"); r.add_argument("--last", type=int, default=0); r.add_argument("--type", choices=TYPES)
r.add_argument("--from", dest="sender"); r.set_defaults(fn=read)
a = ap.parse_args(); a.fn(a)
