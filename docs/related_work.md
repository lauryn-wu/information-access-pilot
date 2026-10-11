# Scope and related work

This is a preliminary positioning note, not a novelty certificate or an exhaustive literature review.

**Strategy fusion is established.** Cowling, Powley and Whitehouse, [Information Set Monte Carlo Tree Search (2012)](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf), discuss the problem of combining state-specific decisions that are not available to a player who cannot distinguish those states. The mathematical error and the need to enforce information sets are not new contributions of this project.

**LLM information-seeking and partial-observation planning are active adjacent topics.** [Uncertainty of Thoughts: Uncertainty-Aware Planning Enhances Information Seeking in Large Language Models](https://arxiv.org/abs/2402.03271) uses an external planning framework to handle uncertain futures. [Belief-State Engine: Augmenting LLMs for Principled Planning Under Partial Observability](https://arxiv.org/abs/2609.10036) studies external belief-state support. These are relevant comparisons; neither title alone establishes whether the particular matched native-model signature tested here is already known.

The prospective contribution would be a reproducible behavioral account of when native LLM choices match an inadmissible perfect-information computation, plus interventions that distinguish it from alternatives. This small screen only checks whether that direction is worth pursuing. Detecting a few wrong choices, or reimplementing a belief-state planner, would not by itself establish that contribution.

## API sources for the implementation

Reviewed October 11, 2026:

- [Claude Sonnet 5.5 model details and rates](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
- [Claude Sonnet 5.5 migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide): adaptive thinking and total output limits.
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create) and [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting).
- [Gemini 3.8 Flash Generate Content guide](https://ai.google.dev/gemini-api/docs/generate-content/latest-model): native REST endpoint, thinking controls and introductory pricing dates.
- [Gemini thinking](https://ai.google.dev/gemini-api/docs/generate-content/thinking): combined output/thinking cap and usage reporting.
- [Gemini token counting](https://ai.google.dev/gemini-api/docs/generate-content/tokens) and [pricing](https://ai.google.dev/gemini-api/docs/pricing).

The adapters are checked offline against the documented request and response structures. They have not yet been validated with paid requests in this project.
