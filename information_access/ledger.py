"""Durable, conservative spending reservations, bound to an immutable manifest."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sqlite3

from .tasks import canonical

NANO = 1_000_000_000


def dollars_to_nano(value):
    number = Decimal(str(value)) * NANO
    if not number.is_finite() or number < 0:
        raise ValueError("Money must be finite and nonnegative")
    return int(number.to_integral_value(rounding=ROUND_CEILING))


def cost(model, input_tokens, output_tokens):
    usd = (Decimal(str(model["input_usd_per_million"])) * input_tokens +
           Decimal(str(model["output_usd_per_million"])) * output_tokens) / 1_000_000
    return dollars_to_nano(usd)


def money(nano):
    return f"{Decimal(nano) / NANO:.6f}"


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def run_lock(directory):
    """Linux/macOS advisory lock; released by the OS even after an interrupted run."""
    import fcntl
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another process is using this run directory") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class BudgetExhausted(RuntimeError):
    pass


class Ledger:
    def __init__(self, directory, manifest):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "ledger.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY, model TEXT NOT NULL, cell TEXT NOT NULL,
            started TEXT NOT NULL, finished TEXT, status TEXT NOT NULL,
            reserved INTEGER NOT NULL, actual INTEGER, counted_input INTEGER NOT NULL,
            choice TEXT, detail TEXT, raw TEXT,
            input_tokens INTEGER, output_tokens INTEGER
          );
        """)
        existing = self.db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()
        encoded = canonical(manifest)
        if existing and existing[0] != encoded:
            self.db.close()
            raise ValueError("Run manifest changed; resume requires the original code, config, and dataset")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('manifest', ?)", (encoded,))
        self.manifest = manifest
        self.limit = dollars_to_nano(manifest["config"]["budget_usd"])

    def close(self):
        self.db.close()

    def attempts(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM attempts ORDER BY id")]

    def exposure(self):
        return self.db.execute("SELECT COALESCE(SUM(MAX(reserved, COALESCE(actual, 0))),0) FROM attempts").fetchone()[0]

    def reserve(self, model, cell, amount, counted_input, retry=False):
        # The caller holds run_lock. The transaction also makes the budget check atomic.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute("SELECT status FROM attempts WHERE model=? AND cell=?", (model, cell)).fetchall()
            if any(row[0] == "valid" for row in previous):
                self.db.rollback()
                return None
            if previous and (not retry or len(previous) >= self.manifest["config"]["max_attempts_per_cell"]):
                self.db.rollback()
                return None
            if self.exposure() + amount > self.limit:
                raise BudgetExhausted("Next request would exceed the shared reservation limit")
            cursor = self.db.execute("""INSERT INTO attempts
                (model,cell,started,status,reserved,counted_input) VALUES (?,?,?,'pending',?,?)""",
                (model, cell, now(), amount, counted_input))
            self.db.commit()  # Must be durable BEFORE generation can be sent.
            return cursor.lastrowid
        except BaseException:
            self.db.rollback()
            raise

    def finish(self, attempt, *, status, choice=None, actual=None, detail=None,
               raw=None, input_tokens=None, output_tokens=None):
        with self.db:
            self.db.execute("""UPDATE attempts SET finished=?,status=?,choice=?,actual=?,detail=?,raw=?,
                input_tokens=?,output_tokens=? WHERE id=?""",
                (now(), status, choice, actual, detail, canonical(raw) if raw is not None else None,
                 input_tokens, output_tokens, attempt))


def read_run(directory):
    path = Path(directory) / "ledger.sqlite3"
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        manifest = json.loads(db.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        attempts = [dict(row) for row in db.execute("SELECT * FROM attempts ORDER BY id")]
        return manifest, attempts
    finally:
        db.close()
