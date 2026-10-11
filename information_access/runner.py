"""Sequential, resumable screen with one shared budget across both providers."""

from datetime import date
import hashlib
import json
from pathlib import Path

from .analysis import analyze
from .ledger import BudgetExhausted, Ledger, cost, dollars_to_nano, money, run_lock
from .providers import NativeProvider, ProviderError, Result
from .tasks import canonical, digest, generate, save_cases


def load_config(path):
    config = json.loads(Path(path).read_text())
    if not 0 < dollars_to_nano(config["budget_usd"]) <= dollars_to_nano("5.00"):
        raise ValueError("This screen's shared budget must be positive and at most $5")
    if config["max_input_tokens"] <= config["input_margin_tokens"] or config["input_margin_tokens"] < 256:
        raise ValueError("Keep at least 256 tokens of input headroom")
    if config["max_output_tokens"] < 4096:
        raise ValueError("Do not shrink the thinking/output allowance below 4096")
    if config["max_attempts_per_cell"] not in (1, 2):
        raise ValueError("At most two attempts per cell")
    if len({m["name"] for m in config["models"]}) != len(config["models"]) or not config["models"]:
        raise ValueError("Model names must be nonempty and unique")
    supported = {"anthropic": "claude-sonnet-5-5", "gemini": "gemini-3.8-flash"}
    for model in config["models"]:
        if supported.get(model["provider"]) != model["model"]:
            raise ValueError("A different model needs a reviewed adapter and pricing")
        if model["effort"] not in ("low", "medium", "high"):
            raise ValueError("Unsupported thinking effort")
        for field in ("input_usd_per_million", "output_usd_per_million"):
            if dollars_to_nano(model[field]) <= 0:
                raise ValueError("Paid model rates must be positive")
    date.fromisoformat(config["pricing_checked"])
    date.fromisoformat(config["pricing_valid_through"])
    return config


def code_hash():
    h = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        h.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def manifest_for(config, cases, mode):
    return {"config": config, "dataset_sha256": digest(cases), "code_sha256": code_hash(), "mode": mode}


def plan(config, cases):
    prices = {m["name"]: cost(m, config["max_input_tokens"], config["max_output_tokens"]) for m in config["models"]}
    initial = sum(prices.values()) * len(cases)
    return {"cells_per_model": len(cases), "models": [m["model"] for m in config["models"]],
            "generation_requests": len(cases) * len(prices),
            "per_request_reserved_usd": {k: money(v) for k, v in prices.items()},
            "first_pass_reserved_usd": money(initial),
            "shared_budget_usd": config["budget_usd"],
            "first_pass_fits": initial <= dollars_to_nano(config["budget_usd"]),
            "retry_headroom_usd": money(max(0, dollars_to_nano(config["budget_usd"]) - initial)),
            "max_output_tokens_including_thinking": config["max_output_tokens"],
            "pricing_valid_through": config["pricing_valid_through"],
            "dataset_sha256": digest(cases), "network_requests_made": 0}


def run(config, cases, directory, *, selected=None, retry=False, limit=None,
        mode="live", provider_factory=NativeProvider, progress=print):
    if mode == "live" and date.today() > date.fromisoformat(config["pricing_valid_through"]):
        raise ValueError("Pricing snapshot expired: verify rates and update config before a new run")
    models = [m for m in config["models"] if selected is None or m["name"] in selected]
    if not models or (selected is not None and set(selected) - {m["name"] for m in models}):
        raise ValueError("Unknown model name")
    if limit is not None and limit < 1:
        raise ValueError("Limit must be positive")
    if mode not in ("live", "simulation:feasible", "simulation:perfect_information", "simulation:fixed_action"):
        raise ValueError("Unknown run mode")
    directory = Path(directory)
    manifest = manifest_for(config, cases, mode)
    with run_lock(directory):
        ledger = Ledger(directory, manifest)
        try:
            cases_path = directory / "cases.jsonl"
            if cases_path.exists():
                frozen = [json.loads(line) for line in cases_path.read_text().splitlines()]
                if digest(frozen) != manifest["dataset_sha256"]:
                    raise ValueError("Frozen cases changed")
            else:
                save_cases(cases_path, cases)
            (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            # Validate all requested credentials before sending the first generation.
            providers = {m["name"]: provider_factory(m, config) for m in models} if mode == "live" else {}
            sent = 0
            prior = ledger.attempts()
            history = {}
            for row in prior:
                history.setdefault((row["model"], row["cell"]), []).append(row)
            for i, case in enumerate(cases):
                # Interleave models so a short smoke run checks both adapters.
                for model in models if i % 2 == 0 else list(reversed(models)):
                    name = model["name"]
                    previous = history.get((name, case["id"]), [])
                    if any(r["status"] == "valid" for r in previous):
                        continue
                    if previous and (not retry or len(previous) >= config["max_attempts_per_cell"]):
                        continue
                    if limit is not None and sent >= limit:
                        return analyze(directory)
                    amount = cost(model, config["max_input_tokens"], config["max_output_tokens"]) if mode == "live" else 0
                    # Pending, failed and interrupted requests keep their entire reservation.
                    if ledger.exposure() + amount > ledger.limit:
                        progress("Stopped: next request would exceed the shared budget.")
                        return analyze(directory)
                    counted = providers[name].count(case["prompt"]) if mode == "live" else 0
                    if counted + config["input_margin_tokens"] > config["max_input_tokens"]:
                        raise ValueError(f"Input too large for {name}/{case['id']}; no generation sent")
                    attempt = ledger.reserve(name, case["id"], amount, counted, retry=retry)
                    if attempt is None:
                        continue
                    sent += 1
                    progress(f"{name}: {case['id']} | reserved ${money(ledger.exposure())} / ${config['budget_usd']}")
                    try:
                        if mode == "live":
                            result = providers[name].generate(case["prompt"])
                        else:
                            policy = mode.split(":", 1)[1]
                            semantic = case["gold"]["choices"][policy]
                            label = next(k for k, v in case["labels"].items() if v == semantic)
                            result = Result("valid", label, canonical({"choice": label}), "SIMULATED", 0, 0,
                                            {"synthetic": True, "policy": policy, "choice": label})
                    except ProviderError as exc:
                        ledger.finish(attempt, status="transport_error", detail=str(exc))
                        raise ValueError(f"{exc}; stopped to avoid repeated failed requests. Resume after resolving it.") from None
                    actual = cost(model, result.input_tokens, result.output_tokens) if (
                        result.input_tokens is not None and result.output_tokens is not None) else None
                    ledger.finish(attempt, status=result.status, choice=result.choice, actual=actual,
                                  detail=result.stop, raw=result.raw, input_tokens=result.input_tokens,
                                  output_tokens=result.output_tokens)
                    if mode == "live" and ((actual is not None and actual > amount)
                        or (result.input_tokens or 0) > config["max_input_tokens"]
                        or (result.output_tokens or 0) > config["max_output_tokens"]):
                        raise ValueError("Provider usage exceeded the reservation assumptions; halted for review")
            return analyze(directory)
        finally:
            ledger.close()
