# Information-access pilot

Does a language model choose a plan as though it will observe a hidden state before acting, even when that information arrives too late or never arrives?

**Status: Sonnet screen completed with no replicated failure signature; Gemini run incomplete.** Sonnet chose the correct action in **63/64 cases**, passed **40/40 control cases**, and showed the predicted joint failure pattern in **0/8 matched pairs**. Gemini produced only two valid responses before repeated provider failures prevented completion.

The repository contains the frozen tasks, exact reference policies, model adapters, raw responses, and analysis. See the [saved results](results/2026-10-11-information-access/).

## Task and comparison

Each task asks the model to choose between a safe option and a plan whose value depends on a hidden state. Information about that state arrives before the decision, provides only partial information, arrives after the decision, or never arrives. An exact rational oracle scores the best policy that can use only the information actually available at decision time.

Eight matched pairs span machine-repair and delivery-routing framings, with four information regimes and two worlds per pair: **64 prompts per model**. The two framings are mathematical analogues, so they do not establish generalization across independent domains.

The primary outcome is a paired pattern of choosing as though unavailable information could guide later action, while passing the information-use controls. Aggregate accuracy alone is insufficient: an always-safe policy already gets 81.25% of the cells right. The [protocol](docs/protocol.md) specifies the signature and continuation criteria.

## Results

| Measure | Sonnet | Gemini |
| --- | ---: | ---: |
| Model | `claude-sonnet-5-5` | `gemini-3.8-flash` |
| Valid responses / planned cells | 64/64 | 2/64 |
| Complete matched pairs | 8/8 | 0/8 |
| Control cases correct / planned | 40/40 | 1/40 |
| Overall accuracy among valid responses | 63/64 | Insufficient coverage |
| Matched pairs showing the joint failure signature | 0/8 | Not estimable |
| Outcome | `no_replicated_signature` | `incomplete` |

Sonnet was correct on 16/16 cases each in the before, after, and never regimes, and 15/16 in the partial-information regime. Both Gemini responses were correct, but three transport failures and missing cells leave no basis for a scientific conclusion about that model. Errors and missing responses are not counted as wrong decisions.

Recorded usage cost was **$0.171051**, with **three attempts of unknown cost**. The conservative reservation was **$2.961740** against the shared $5 cap. Recorded usage is therefore not a complete invoice estimate.

## Parsing audit

The initial parser rejected two Sonnet responses that ended with the requested JSON after an explanation. A documented offline recovery accepted terminal JSON under a uniform rule, without rerunning either response. Raw responses, original statuses, timestamps, usage, and reservations were preserved; the source-code transition is recorded in [format_recovery.json](results/2026-10-11-information-access/format_recovery.json).

The 64 valid Sonnet cells above include those two recovered responses. They are original provider responses, not replacement samples. The [full analysis](results/2026-10-11-information-access/analysis.json) includes the recovery record and reports Gemini's incompleteness separately.

## Interpretation and status

This completed Sonnet run did not show the proposed information-access error under the tested prompts and settings. Its one mistake occurred under partial information and did not produce the prespecified joint pattern. Eight matched pairs provide limited coverage; the result does not establish that the model always respects information constraints.

The Sonnet screen is complete and the Gemini portion remains incomplete. No further experiments are currently planned for this design. The repository preserves both outcomes, without treating the combined study as a completed two-model comparison. See [related work](docs/related_work.md) for the hypothesis and its limits.

## Inspect and reproduce the results

Python 3.11+ on macOS or Linux is sufficient; there are no third-party runtime dependencies. The [offline reproduction instructions](docs/REPRODUCING_RESULTS.md) recompute the saved analysis from committed cases and attempts, including the parsing-recovery record. No credentials or API calls are needed.

For software checks and a preview of the frozen plan:

```bash
python3 -m unittest discover -s tests -v
python3 -m information_access plan
```

The original [run instructions](docs/RUNNING.md) cover optional live execution, synthetic reference policies, recovery, and the spending guard. Only `run --execute` can send model API requests. Synthetic demonstrations are separate from the model results above.
