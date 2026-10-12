# Reproduce the saved information-access analysis

The committed cases and attempts are sufficient to reproduce the report without API access. Run the following from the repository root with Python 3.11+. It verifies the frozen dataset hash, recomputes both model reports, attaches the recorded parsing-recovery metadata, and compares the entire result with the committed analysis. It does not change any file or create a spending ledger.

```bash
python3 - <<'PY'
import json
from pathlib import Path
from information_access.analysis import summarize
from information_access.tasks import digest

root = Path("results/2026-10-11-information-access")
manifest = json.loads((root / "manifest.json").read_text())
cases = [json.loads(line) for line in (root / "cases.jsonl").read_text().splitlines()]
attempts = [json.loads(line) for line in (root / "attempts.jsonl").read_text().splitlines()]
if digest(cases) != manifest["dataset_sha256"]:
    raise SystemExit("Frozen dataset hash does not match.")
recomputed, _ = summarize(cases, manifest["config"]["models"], attempts, manifest["mode"])
recomputed["format_recovery"] = json.loads((root / "format_recovery.json").read_text())
saved = json.loads((root / "analysis.json").read_text())
if recomputed != saved:
    raise SystemExit("Saved and recomputed analyses differ.")
print("Saved analysis reproduced exactly.")
for name, report in recomputed["models"].items():
    print(name, report["outcome"], f"{report['valid_cells']}/{report['total_cells']} valid")
PY
```

Expected: Sonnet `no_replicated_signature` with 64/64 valid cells; Gemini `incomplete` with 2/64 valid cells.

The two recovered Sonnet responses are included in the exported attempts. Their original invalid-format statuses and the code-hash transition are retained in `format_recovery.json`. The run manifest preserves the original source hash. `checkout-at-archive.txt` records the checkout used when committing the export, not necessarily the source used for every request.

The operational `analyze` command reads a local SQLite ledger, which is intentionally absent from this export. Use the read-only command above for the committed results. The original ledger is required for operational resumption and budget tracking; the export is not a fresh spending allowance.
