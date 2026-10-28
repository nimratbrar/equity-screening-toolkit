"""Prompt for your WRDS username and password (hidden input) and save them to ~/.pgpass with 600 permissions.

Run it yourself in your own terminal, never through a chat or an agent:
    ~/.venvs/equity-screening-toolkit/bin/python store_password.py

Equivalent to the wrds package's own `wrds.Connection().create_pgpass_file()`, without opening a connection.
Other lines already in ~/.pgpass are kept; only an existing WRDS line is replaced.
"""
import getpass
import os
from pathlib import Path

HOST, PORT, DB = "wrds-pgdata.wharton.upenn.edu", "9737", "wrds"   # public WRDS PostgreSQL endpoint

user = os.environ.get("WRDS_USERNAME") or input("WRDS username: ").strip()
pw = getpass.getpass("WRDS password (hidden): ")
path = Path(os.environ.get("PGPASSFILE", Path.home() / ".pgpass"))
esc = lambda v: v.replace("\\", "\\\\").replace(":", "\\:")   # pgpass format: escape backslash and colon
keep = [ln for ln in (path.read_text().splitlines() if path.exists() else []) if not ln.startswith(f"{HOST}:")]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # created 600, never world-readable, even briefly
os.fchmod(fd, 0o600)
with os.fdopen(fd, "w") as fh:
    fh.write("\n".join(keep + [f"{HOST}:{PORT}:{DB}:{esc(user)}:{esc(pw)}"]) + "\n")
print(f"Saved to {path} (permissions 600). The password was not printed or logged.")
