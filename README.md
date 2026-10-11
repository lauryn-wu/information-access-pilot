# Information-access pilot

**Does an LLM choose a plan as though it will observe a hidden state before acting, even when that information arrives too late or never arrives?**

This repository implements a small, falsifiable diagnostic screen. It contains **no empirical model results**. The hypothesis is uncertain; strong models may solve every case. A positive screen would justify a more careful follow-up, not establish an internal algorithm, novelty, or conference readiness.

## What is included

- 8 matched pairs, each under 4 information regimes, giving 64 prompts per model.
- Two surface framings: machine repair and delivery routing. These are mathematical analogues, not independent problem domains.
- Exact rational gold values over admissible observation-dependent policies.
- Native Anthropic and Gemini REST adapters with reasoning enabled.
- A persistent **$5 shared reservation limit**, including failed calls and explicit retries.
- Raw responses, frozen prompts/configuration, usage accounting, and paired analysis.
- Offline reference policies and tests; no third-party runtime dependencies.

## Quick start: entirely offline

Python 3.11+ on macOS or Linux. From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m information_access plan
python3 -m information_access demo --policy feasible
python3 -m information_access demo --policy perfect_information
python3 -m information_access demo --policy fixed_action
```

The feasible reference should score 100% and produce no diagnostic signatures. The perfect-information reference should produce all 8 signatures. The fixed-action reference should fail the information-use controls. **These are synthetic software checks, not model measurements.**

The frozen screen is in [`data/screen.jsonl`](data/screen.jsonl). Regenerate it with:

```bash
python3 -m information_access generate
```

## Paid screen, when ready

Set `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` in your shell. Keys are read only from environment variables; `.env` files are not loaded. Never commit a key.

Start with four generation requests to check provider access and response formatting:

```bash
python3 -m information_access run --execute --limit 4
```

Continue the same run, using the same directory and reservation ledger:

```bash
python3 -m information_access run --execute
python3 -m information_access analyze
```

To run just one provider first, use `--model sonnet` or `--model gemini`. Later omit `--model` to complete the other provider within the **same** shared budget. The smoke calls are part of the screen, not extra trials.

There are no automatic generation retries. A resumed run skips attempted cells by default. After checking an error, allow one retry per failed/invalid cell with:

```bash
python3 -m information_access run --execute --retry-failed
```

A valid answer is never resampled, even when it is wrong. An interrupted call keeps its full reservation because the provider may have charged for it. Retries use the original prompt and settings. Frequent truncation is a reason to revise the screen's allocation, not evidence of a reasoning failure.

## Cost envelope

The checked-in configuration uses rates verified on **2026-10-11**:

| Model | Thinking setting | Input / 1M tokens | Output / 1M tokens | Reservation for 64 calls |
|---|---|---:|---:|---:|
| `claude-sonnet-5-5` | Adaptive, high effort | $2.00 | $10.00 | $2.87744 |
| `gemini-3.8-flash` | Medium thinking | $0.75 | $3.75 | $1.07904 |
| **First pass total** | | | | **$3.95648** |

Each generation reserves **2,000 input + 4,096 total output tokens, including thinking**. A native token-count request runs first; the count plus 256 tokens of headroom must fit the input allowance. Prompts are under 1,200 UTF-8 bytes. No search, tools, explicit caches, or other billable features are enabled.

All reservations remain charged against the local $5 limit, even when reported usage is lower. This deliberately conservative rule leaves **$1.04352** for retry reservations. The process stops before a request that would exceed the limit. Unknown charges are never treated as zero.

This is a software spending guard at the recorded API rates, not a provider billing limit. It does not cover taxes, exchange rates, other applications, or separate run directories. Retain `runs/screen/`; deleting it or starting a new directory starts a separate budget. Unexpected usage beyond the configured bounds halts execution for review.

The pricing snapshot expires **2026-11-10**, when live runs refuse to continue until rates are reviewed. Gemini's current introductory prices end December 31, 2026. See the [Anthropic model documentation](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). Settings, code and dataset hashes are frozen per run; changing them requires a separately identified run and budget.

## What to inspect

Under `runs/screen/`:

| File | Contents |
|---|---|
| `manifest.json` | Frozen configuration, code hash, dataset hash, live/simulation mode |
| `cases.jsonl` | Exact prompts, matched factors, gold choices and values |
| `ledger.sqlite3` | Durable attempts and reservations; the authoritative run state |
| `attempts.jsonl` | Exported raw provider responses, timestamps, token usage, statuses |
| `decisions.csv` | One row per planned model/cell; missing choices stay empty |
| `analysis.json` | Control accuracy, paired signatures, policy agreement, cost accounting |

After an interrupted/error exit, `analyze` exports all stored attempts, including pending ones. The SQLite ledger is saved before every generation request. Only prompt text is sent to providers; gold answers and condition labels are never sent.

`invalid_format`, `truncated`, `blocked`, `incomplete_response`, `malformed_response`, transport failures and pending requests are **not scored as wrong decisions**. The descriptive report uses the first valid response per cell and separately reports first-attempt validity and all attempt statuses.

The main outcome is the **paired signature**, not aggregate accuracy. An always-safe policy already gets 81.25% of these cells right. See [`docs/protocol.md`](docs/protocol.md) for the frozen decision rule and [`docs/related_work.md`](docs/related_work.md) for the scope of the proposed contribution.

## Implementation notes

`information_access/tasks.py` generates and solves tasks; `providers.py` handles the native APIs; `ledger.py` reserves spending; `runner.py` executes/resumes; `analysis.py` reports the paired outcomes. The CLI does not make network calls unless `run --execute` is supplied. The synthetic demos cannot be resumed as live experiments.

There is intentionally no automated paid workflow. Offline tests check exact values, matching, parsing, hidden-token accounting, budget persistence, crash recovery, duplicate prevention and the synthetic reference signatures. Live access, model availability, and actual response validity still need the four-call smoke check.
