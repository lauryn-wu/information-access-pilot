"""Descriptive paired diagnostics; invalid requests never become reasoning errors."""

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from .ledger import money, read_format_recovery, read_run
from .tasks import FAMILIES, REGIMES, digest


def summarize(cases, models, attempts, mode="live"):
    valid = {}
    for row in attempts:
        if row["status"] == "valid":
            valid.setdefault((row["model"], row["cell"]), row)
    reports, rows = {}, []
    for model in models:
        name = model["name"]
        decisions, grouped = {}, defaultdict(dict)
        for case in cases:
            record = valid.get((name, case["id"]))
            label = record["choice"] if record else None
            choice = case["labels"].get(label)
            decisions[case["id"]] = choice
            grouped[case["pair"]][(case["world"], case["regime"])] = case
            rows.append({"model": name, "cell": case["id"], "family": case["family"],
                         "world": case["world"], "regime": case["regime"],
                         "choice": choice or "", "gold": case["gold"]["choices"]["feasible"],
                         "correct": int(choice == case["gold"]["choices"]["feasible"]) if choice else ""})

        def accuracy(subset, policy="feasible"):
            observed = [c for c in subset if decisions[c["id"]] is not None]
            correct = sum(decisions[c["id"]] == c["gold"]["choices"][policy] for c in observed)
            return {"correct": correct, "valid": len(observed), "total": len(subset),
                    "rate": correct / len(observed) if observed else None}

        paired = []
        for pair, cells in sorted(grouped.items()):
            def get(world, regime):
                return decisions[cells[(world, regime)]["id"]]
            complete = all(get(w, r) is not None for w in ("aligned", "crossed")
                           for r in ("before", "after", "never"))
            controls_ok = get("aligned", "before") == "safe" and get("crossed", "before") == "plan"
            signature = {}
            for regime in ("after", "never"):
                observable = all(get(w, regime) is not None for w in ("aligned", "crossed"))
                signature[regime] = (get("aligned", regime) == "safe" and get("crossed", regime) == "plan") if observable else None
            paired.append({"pair": pair, "family": cells[("aligned", "before")]["family"],
                           "complete": complete, "before_controls_correct": controls_ok,
                           "after_signature": signature["after"], "never_signature": signature["never"],
                           "joint_signature": complete and controls_ok and all(signature.values())})
        controls = accuracy([c for c in cases if c["world"] == "aligned" or c["regime"] == "before"])
        observed = sum(v is not None for v in decisions.values())
        signatures = Counter(p["family"] for p in paired if p["joint_signature"])
        if observed < len(cases):
            outcome = "incomplete"
        elif controls["rate"] < 0.90:
            outcome = "control_failure"
        elif sum(signatures.values()) >= 2 and all(signatures[f] >= 1 for f in FAMILIES):
            outcome = "signal_to_recheck"
        else:
            outcome = "no_replicated_signature"
        model_attempts = [r for r in attempts if r["model"] == name]
        first = {}
        for row in model_attempts:
            first.setdefault(row["cell"], row)
        reports[name] = {
            "outcome": outcome, "valid_cells": observed, "total_cells": len(cases),
            "attempt_status_counts": dict(Counter(r["status"] for r in model_attempts)),
            "first_attempt_valid_cells": sum(r["status"] == "valid" for r in first.values()),
            "control_accuracy": controls,
            "accuracy_by_regime": {r: accuracy([c for c in cases if c["regime"] == r]) for r in REGIMES},
            "policy_agreement": {p: accuracy(cases, p) for p in ("feasible", "perfect_information", "fixed_action")},
            "complete_pairs": sum(p["complete"] for p in paired),
            "joint_signature_pairs": sum(signatures.values()),
            "joint_signature_by_family": {f: signatures[f] for f in FAMILIES},
            "pairs": paired,
        }
    actual = sum(r["actual"] or 0 for r in attempts)
    exposure = sum(max(r["reserved"], r["actual"] or 0) for r in attempts)
    return {"mode": mode, "models": reports, "cost": {
        "reserved_exposure_usd": money(exposure), "known_usage_cost_usd": money(actual),
        "unknown_cost_attempts": sum(r["actual"] is None for r in attempts)},
        "interpretation": "Exploratory screen only; signatures do not establish an internal algorithm or novelty."}, rows


def analyze(directory):
    directory = Path(directory)
    manifest, attempts = read_run(directory)
    cases = [json.loads(line) for line in (directory / "cases.jsonl").read_text().splitlines()]
    if digest(cases) != manifest["dataset_sha256"]:
        raise ValueError("Frozen dataset was modified")
    report, rows = summarize(cases, manifest["config"]["models"], attempts, manifest["mode"])
    recovery = read_format_recovery(directory)
    if recovery:
        report["format_recovery"] = recovery
        (directory / "format_recovery.json").write_text(json.dumps(recovery, indent=2) + "\n")
    (directory / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    with (directory / "decisions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (directory / "attempts.jsonl").open("w") as handle:
        for row in attempts:
            row["raw"] = json.loads(row["raw"]) if row["raw"] else None
            handle.write(json.dumps(row) + "\n")
    return report
