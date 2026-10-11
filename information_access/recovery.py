"""One audited, offline correction for the original terminal-JSON parser."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .analysis import analyze
from .ledger import (FORMAT_RECOVERY_KEY, approved_format_transition, now,
                     read_format_recovery, read_run, recovered_manifest_matches, run_lock)
from .providers import decode
from .runner import manifest_for
from .tasks import canonical, digest


def recover_format(config, cases, directory):
    """Reparse stored invalid-format responses without changing any API request."""
    directory = Path(directory)
    if not (directory / "ledger.sqlite3").is_file():
        raise ValueError("No existing ledger to recover; use the original run directory")
    with run_lock(directory):
        original, attempts = read_run(directory)
        current = manifest_for(config, cases, "live")
        frozen = [json.loads(line) for line in (directory / "cases.jsonl").read_text().splitlines()]
        if digest(frozen) != original["dataset_sha256"]:
            raise ValueError("Frozen dataset was modified")
        if json.loads((directory / "manifest.json").read_text()) != original:
            raise ValueError("Exported manifest differs from the ledger")
        audit = read_format_recovery(directory)
        if audit:
            if not recovered_manifest_matches(original, current, audit):
                raise ValueError("Recovery does not authorize this code, config, dataset, or mode")
            applied = False
        elif original == current:
            # A new run already uses this parser and needs no migration.
            applied = False
        else:
            if not approved_format_transition(original, current):
                raise ValueError("No approved parser recovery for this code, config, dataset, or mode")
            providers = {m["name"]: m["provider"] for m in original["config"]["models"]}
            changes = []
            for row in attempts:
                if row["status"] not in ("valid", "invalid_format"):
                    continue
                if row["raw"] is None or row["model"] not in providers:
                    raise ValueError("Missing raw response or unknown model; cannot recover safely")
                result = decode(providers[row["model"]], json.loads(row["raw"]))
                if (result.stop, result.input_tokens, result.output_tokens) != (
                        row["detail"], row["input_tokens"], row["output_tokens"]):
                    raise ValueError("Recovery would change stop/usage accounting; review required")
                if row["status"] == "valid":
                    if (result.status, result.choice) != ("valid", row["choice"]):
                        raise ValueError("Recovery would change an existing valid answer; review required")
                elif result.status == "valid":
                    changes.append({"attempt_id": row["id"], "model": row["model"], "cell": row["cell"],
                                    "original_status": row["status"], "original_choice": row["choice"],
                                    "status": result.status, "choice": result.choice,
                                    "raw_sha256": hashlib.sha256(row["raw"].encode()).hexdigest()})
                elif result.status != "invalid_format":
                    raise ValueError("Recovery would change a provider status; review required")
            backup = directory / f"ledger.before-format-v2-{uuid4().hex}.sqlite3"
            audit = {"id": FORMAT_RECOVERY_KEY, "applied_at": now(),
                     "from_code_sha256": original["code_sha256"], "to_code_sha256": current["code_sha256"],
                     "after_attempt_id": max((r["id"] for r in attempts), default=0),
                     "original_attempt_status_counts": {
                         name: dict(Counter(r["status"] for r in attempts if r["model"] == name))
                         for name in providers},
                     "changes": changes, "backup_file": backup.name, "network_requests_made": 0}
            db = sqlite3.connect(directory / "ledger.sqlite3")
            try:
                db.execute("PRAGMA synchronous=FULL")
                # The same exclusive run lock is held by both recovery and generation.
                # Back up first; statuses/choices and their audit then commit atomically.
                with backup.open("xb"):
                    pass
                saved = sqlite3.connect(backup)
                try:
                    db.backup(saved)
                finally:
                    saved.close()
                with db:
                    for change in changes:
                        db.execute("UPDATE attempts SET status=?,choice=? WHERE id=?",
                                   (change["status"], change["choice"], change["attempt_id"]))
                    db.execute("INSERT INTO metadata VALUES (?,?)", (FORMAT_RECOVERY_KEY, canonical(audit)))
            finally:
                db.close()
            applied = True
        report = analyze(directory)
        return {"recovery_applied": applied, "recovered_attempts": len(audit["changes"]) if audit else 0,
                "network_requests_made": 0,
                "valid_cells": {name: m["valid_cells"] for name, m in report["models"].items()},
                "cost": report["cost"],
                "backup_file": audit["backup_file"] if audit else None}
