# Information-access pilot

This pilot tests whether a model chooses a plan that would require information
it cannot obtain before acting. Sonnet answered 63/64 cases correctly and showed
the predicted failure pattern in none of the eight matched pairs. The Gemini run
stopped after provider failures, with only two valid responses.

The tasks, reference policies, model adapters, raw responses, and analysis are
included here. Start with the [saved results](results/2026-10-11-information-access/).

## Task and comparison

Each task offers a safe option and a plan whose value depends on a hidden state.
Information about that state arrives before the decision, provides only partial
information, arrives after the decision, or never arrives. A reference solver
computes the best policy using only information available at decision time.

Eight matched pairs use machine-repair and delivery-routing scenarios, with four
information regimes and two worlds per pair: 64 prompts per model. The scenarios
are two framings of the same mathematical task.

The planned failure pattern requires the model to choose as though unavailable
information could guide later action, while passing the corresponding controls.
Accuracy alone would miss this distinction: always choosing the safe option
already gets 81.25% of cases right. The [protocol](docs/protocol.md) defines the
pattern and the criteria for continuing.

## Results

| Measure | Sonnet | Gemini |
| --- | ---: | ---: |
| Model | `claude-sonnet-5-5` | `gemini-3.8-flash` |
| Valid responses / planned cases | 64/64 | 2/64 |
| Complete matched pairs | 8/8 | 0/8 |
| Control cases correct / valid | 40/40 | 1/1; 39 missing |
| Overall accuracy among valid responses | 63/64 | Insufficient coverage |
| Matched pairs showing the planned failure pattern | 0/8 | Not estimable |
| Outcome | `no_replicated_signature` | `incomplete` |

Sonnet was correct on 16/16 cases each in the before, after, and never regimes,
and 15/16 with partial information. Both Gemini responses were correct, but
three transport failures left the run too incomplete to assess its behavior.
Missing responses are excluded from accuracy.

Known usage charges totalled $0.171051; three attempts have unknown cost. The
budget guard's conservative reservation was $2.961740 against a shared $5 cap.

## Recovered JSON responses

The first parser rejected two Sonnet responses that gave an explanation before
the requested JSON. An offline parsing change accepted terminal JSON under a
uniform rule, without rerunning either response. Both are included in the 64
valid responses above. The raw outputs, original statuses, timestamps, usage,
and reservations were preserved. The code change is recorded in
[format_recovery.json](results/2026-10-11-information-access/format_recovery.json)
and included in the [analysis](results/2026-10-11-information-access/analysis.json).

## Study status

Sonnet's one mistake, under partial information, did not match the proposed
failure pattern. Eight pairs give limited coverage, and Gemini's incomplete run
prevents a comparison between models. No further runs are planned for this
design. The [related work](docs/related_work.md) explains the hypothesis in more
detail.

## Inspect and reproduce the results

Python 3.11+ on macOS or Linux is sufficient; there are no third-party runtime dependencies. The [offline reproduction instructions](docs/REPRODUCING_RESULTS.md) recompute the saved analysis from committed cases and attempts, including the parsing-recovery record. No credentials or API calls are needed.

For software checks and a preview of the frozen plan:

```bash
python3 -m unittest discover -s tests -v
python3 -m information_access plan
```

The [run instructions](docs/RUNNING.md) cover live execution, scripted reference
policies, recovery, and the spending guard. Only `run --execute` sends model API
requests; the synthetic demonstrations check the software.
