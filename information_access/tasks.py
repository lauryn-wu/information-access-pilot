"""Construct matched worlds and solve policies over observation classes exactly."""

from collections import Counter
from fractions import Fraction
from itertools import product
import hashlib
import json
import random

REGIMES = ("before", "partial", "after", "never")
FAMILIES = ("repair", "routing")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def classes(case):
    n = len(case["payoffs"])
    if case["regime"] == "before":
        return [[s] for s in range(n)]
    if case["regime"] == "partial":
        return case["signal_groups"]
    return [list(range(n))]


def value(case, groups):
    """The initial safe option is NOT available after a signal arrives."""
    p = [Fraction(x) for x in case["priors"]]
    u = case["payoffs"]
    return sum((max(sum(p[s] * u[s][a] for s in group)
                    for a in range(len(u[0]))) for group in groups), Fraction(0))


def solve(case):
    n = len(case["payoffs"])
    values = {"feasible": value(case, classes(case)),
              "perfect_information": value(case, [[s] for s in range(n)]),
              "fixed_action": value(case, [list(range(n))])}
    safe = Fraction(case["safe_points"])
    if any(v == safe for v in values.values()):
        raise ValueError("Tied initial decisions are outside this screen")
    return {"values": {k: str(v) for k, v in values.items()},
            "choices": {k: "plan" if v > safe else "safe" for k, v in values.items()}}


def brute_force_value(case):
    """Independent exhaustive policy enumeration, used only for validation."""
    groups, u = classes(case), case["payoffs"]
    p = [Fraction(x) for x in case["priors"]]
    return max(sum(p[s] * u[s][a] for group, a in zip(groups, policy) for s in group)
               for policy in product(range(len(u[0])), repeat=len(groups)))


def render(case):
    repair = case["family"] == "repair"
    setting = "A machine has a fixed hidden fault" if repair else "A delivery has fixed hidden road conditions"
    action = "repair" if repair else "route"
    n = len(case["payoffs"])
    names = [f"{action[0].upper()}{a+1}" for a in range(len(case["payoffs"][0]))]
    table = "state | " + " | ".join(names) + "\n" + "\n".join(
        f"S{s+1} | " + " | ".join(map(str, row)) for s, row in enumerate(case["payoffs"]))
    timings = {
        "before": f"After entering the process, you learn the exact state BEFORE choosing the {action}.",
        "after": f"You learn the exact state only AFTER choosing and irrevocably executing the {action}.",
        "never": "You receive no information about the state at any time.",
        "partial": f"After entering the process, BEFORE choosing the {action}, a report says " +
            "; ".join(f"{label} for " + ", ".join(f"S{s+1}" for s in group)
                      for label, group in zip(("BLUE", "GOLD"), case["signal_groups"])) +
            ". It never reveals anything else.",
    }
    descriptions = {"safe": f"Receive {case['safe_points']} points for certain; the task ends.",
                    "plan": f"Enter the process, then select exactly one {action} from the table."}
    options = "\n".join(f"{label}: {descriptions[case['labels'][label]]}" for label in ("X", "Y"))
    return (f"Maximize expected total points over independent repetitions.\n"
            f"{setting}. States S1 through S{n} are equally likely; you do not know which is actual.\n"
            f"Choose ONE initial option now, before any report:\n{options}\n"
            f"If you enter the process, you cannot switch to the guaranteed option. "
            f"The table gives the points for each {action} in each state:\n{table}\n"
            f"{timings[case['regime']]}\n"
            f"There are no other observations, actions, or costs. You must select the {action} "
            f"yourself; nobody else can select it for you.\n"
            'Think through the decision. Return only JSON {"choice":"X"} or {"choice":"Y"} '
            "for the initial option.")


def generate(seed=20261011):
    rng = random.Random(seed)
    # n, actions, low, high, safe. Partial-information gold alternates plan/safe.
    templates = [(4, 2, 0, 12, 8), (4, 4, 0, 20, 16),
                 (8, 2, 2, 18, 11), (8, 4, 0, 24, 16)]
    cases = []
    for fi, family in enumerate(FAMILIES):
        for ti, (n, m, low, high, safe) in enumerate(templates):
            low, high, safe = (v * (fi + 1) + 3 * fi for v in (low, high, safe))
            pair = f"{family}-{ti+1:02d}"
            order = rng.sample(range(n), n)
            columns = rng.sample(range(m), m)
            labels = {"X": "safe", "Y": "plan"} if (fi + ti) % 2 == 0 else {"X": "plan", "Y": "safe"}
            isolated = order.index(0)
            groups = [[isolated], [s for s in range(n) if s != isolated]]
            for world in ("aligned", "crossed"):
                payoffs = []
                for s in order:
                    payoffs.append([high if (s if world == "aligned" else
                        (s + a // 2 + (n // 2 if a % 2 else 0)) % n) < n // 2
                        else low for a in columns])
                for regime in REGIMES:
                    case = {"id": f"{pair}-{world}-{regime}", "pair": pair, "family": family,
                            "world": world, "regime": regime, "payoffs": payoffs,
                            "priors": [str(Fraction(1, n))] * n, "safe_points": safe,
                            "signal_groups": groups, "labels": labels}
                    case["gold"] = solve(case)
                    case["prompt"] = render(case)
                    cases.append(case)
    rng.shuffle(cases)
    validate(cases)
    return cases


def validate(cases):
    if len(cases) != 64 or len({c["id"] for c in cases}) != 64:
        raise ValueError("Screen must contain 64 distinct cells")
    pairs = {}
    for c in cases:
        n, m = len(c["payoffs"]), len(c["payoffs"][0])
        if any(len(row) != m for row in c["payoffs"]):
            raise ValueError("Nonrectangular payoff table")
        if len(c["priors"]) != n or sum(map(Fraction, c["priors"])) != 1:
            raise ValueError("Invalid prior")
        if sorted(s for g in c["signal_groups"] for s in g) != list(range(n)):
            raise ValueError("Signals must partition states")
        if c["gold"] != solve(c) or c["prompt"] != render(c):
            raise ValueError("Stale gold or prompt")
        pairs.setdefault(c["pair"], {})[(c["world"], c["regime"])] = c
    for cells in pairs.values():
        if set(cells) != set(product(("aligned", "crossed"), REGIMES)):
            raise ValueError("Incomplete matched pair")
        a, b = cells[("aligned", "never")], cells[("crossed", "never")]
        for column in range(len(a["payoffs"][0])):
            if Counter(row[column] for row in a["payoffs"]) != Counter(row[column] for row in b["payoffs"]):
                raise ValueError("Action marginal mismatch")
        if a["gold"]["values"]["fixed_action"] != b["gold"]["values"]["fixed_action"]:
            raise ValueError("Fixed-action values differ")
        for world in ("aligned", "crossed"):
            reference = cells[(world, "never")]
            for regime in REGIMES:
                c = cells[(world, regime)]
                for key in ("payoffs", "labels", "priors", "safe_points", "signal_groups"):
                    if c[key] != reference[key]:
                        raise ValueError("Timing match changed another factor")
                v = {k: Fraction(v) for k, v in c["gold"]["values"].items()}
                if not v["fixed_action"] <= v["feasible"] <= v["perfect_information"]:
                    raise ValueError("Information value ordering failed")
        if a["gold"]["choices"]["feasible"] != "safe" or b["gold"]["choices"]["perfect_information"] != "plan":
            raise ValueError("Pair lacks diagnostic separation")


def save_cases(path, cases):
    path.write_text("".join(canonical(c) + "\n" for c in cases))
