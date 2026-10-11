# Diagnostic screen v1

Status: frozen before model data collection. Exploratory feasibility screen, not a powered confirmatory experiment. No live results are included in the repository.

## Target computation

The hypothesis is that a model sometimes evaluates a contingent plan by selecting the best action separately in each possible state, without enforcing what it will actually know when choosing the action. The behavioral comparator is the perfect-information relaxation:

\[
V_{PI}=\sum_s p(s)\max_a U(s,a).
\]

The admissible value groups indistinguishable states together:

\[
V_{F}=\sum_o\max_a\sum_{s:g(s)=o}p(s)U(s,a).
\]

With no timely signal, this reduces to:

\[
V_{fixed}=\max_a\sum_s p(s)U(s,a).
\]

The model chooses between a guaranteed payoff and entering the process. This initial choice happens **before** receiving any signal. The guarantee cannot be selected after a signal; entering the process commits the decision maker to choosing one table action. Gold values use exact fractions, not model-generated explanations or a judge model.

## Diagnostic matching

An illustrative two-state pair with equally likely states:

| World | State | Action A | Action B |
|---|---|---:|---:|
| Aligned | 1 | 10 | 10 |
| Aligned | 2 | 0 | 0 |
| Crossed | 1 | 10 | 0 |
| Crossed | 2 | 0 | 10 |

In either world, each fixed action has exactly the same payoff distribution: 0 or 10 with equal probability. A guaranteed 6 therefore wins without timely observation. Under full observation before acting, the aligned process is still worth 5, while the crossed process is worth 10. The perfect-information comparator incorrectly prefers the crossed process without timely observation.

The actual screen uses 4 or 8 equiprobable states and 2 or 4 actions. Aligned columns share the same high/low states; crossed columns have complementary or shifted high/low states. Every action's marginal distribution is matched across the two worlds. State order and action order are shuffled within each pair and then held fixed across regimes. Initial X/Y labels are balanced across pairs and held fixed within each pair. The safe threshold never ties any comparator value.

Each pair is rendered in four regimes:

1. **Before:** exact state revealed after entering, before action selection.
2. **Partial:** report identifies one state or the set of all remaining states before selection.
3. **After:** exact state revealed only after irrevocably executing the action.
4. **Never:** no observation at any time.

Partial information has strictly intermediate value in crossed worlds. Half the partial cells favor the process; half favor the guarantee. After and never have identical feasible values.

There are four numerical templates in each of two surface framings, repair and routing: 8 matched pairs × 2 worlds × 4 regimes = 64 prompts per model. The routing templates are affine payoff transformations of the repair templates. **These are two renderings of four mathematical structures, not eight independent domains or eight independent observations.** No inferential p-values or independence-based confidence intervals are reported.

## Procedure

- Seed 20261011; deterministic shuffled cell order, alternating model order.
- Every prompt starts a fresh stateless request. No demonstrations, feedback, tools, conversations, or model-generated world descriptions.
- The objective is explicitly expected total points across repetitions.
- Collect one response per model/cell. Initial labels only: JSON `{"choice":"X"}` or `{"choice":"Y"}`. Reasoning remains enabled internally.
- Use native model defaults for sampling; the selected APIs do not support the old sampling overrides. Thinking settings are explicit in the config. These are not matched-compute comparisons.
- Output allowance: 4096 tokens including hidden thinking. Truncated output is excluded even if it happens to contain a parseable choice. Do not lower this allowance to elicit failures.
- Up to one identical retry of an invalid/failed request, only by explicit CLI flag and within the same budget. Never resample a valid decision. Record both attempts; analyze the first valid answer, report first-attempt validity separately.
- An expired rate snapshot, modified manifest, oversized input, or unexpected usage stops the run. Rate/authentication errors stop repeated paid requests.

Model identities and versions returned by providers remain in raw responses. Provider IDs may evolve; exact behavioral reproducibility is not guaranteed. Any later study should freeze supported snapshots where available and record collection dates.

## Primary diagnostic and controls

For each pair, the joint signature requires:

- Correct full-reveal choices: aligned → guarantee; crossed → process.
- In **both** after and never: aligned → guarantee; crossed → process.

Thus a model must use information correctly when it is available and show the predicted directional matched error when it is unavailable. A single isolated wrong answer does not satisfy the signature.

Report all eight pair patterns, each after/never signature separately, control accuracy, validity counts, and agreement with the feasible, perfect-information and fixed-action comparators. The common control set is all aligned cells plus the full-reveal crossed cells (40 cells per model). Partial crossed cells provide an additional graded-information check.

The following frozen labels organize the screen; thresholds are pragmatic, not statistical evidence:

| Outcome | Rule per model |
|---|---|
| `incomplete` | Any of the 64 planned cells lacks a valid answer |
| `control_failure` | Complete, but fewer than 90% of the 40 controls are correct |
| `signal_to_recheck` | Complete; controls pass; at least 2 joint signatures, with at least 1 in each surface framing |
| `no_replicated_signature` | Complete and controls pass, but the signature threshold is not met |

Interpret each model separately. A positive result in one model is not replication across models. An all-correct result is a useful negative screen; it does not disprove the phenomenon in every possible setting. A positive label requires manual inspection of the paired prompts, provider validity and competing explanations before allocating more money.

## What this cannot establish

The design constrains simple payoff-risk explanations, but does not prove which internal algorithm generated a response. Correlation-sensitive heuristics, table comprehension, instruction interpretation and ordinary mistakes remain alternatives. Surface replication does not establish broad planning generality. The aligned control is structurally simple, so a more demanding follow-up would need less transparent matched constructions, richer sequential settings, causal interventions and replication on held-out structures.

Do not move thresholds after observing outcomes, hide invalid calls, add only failure-inducing examples, or treat synthetic reference output as model data. A larger pilot or new prompt/intervention variant needs a separately documented protocol and budget; the repository does not launch one automatically.
