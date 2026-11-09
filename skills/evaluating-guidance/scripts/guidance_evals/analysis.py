"""Equal-case paired analysis; only balanced fixed looks k=3,6 authorize verdicts.

Hoeffding intervals concern the frozen panel under independent stable trials,
not unseen tasks. Student-t is descriptive planning evidence, never the decision
criterion. Unknown critical judgments stay unknown and widen score envelopes.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import math
from statistics import mean, stdev
from typing import Literal

from pydantic import Field

from .contracts import StrictModel
from .runner import GradedCheck, Observation

ALPHA = 0.05
RELIABILITY_K = 3
SEPARATION_THRESHOLD = 0.05


class Interval(StrictModel):
    low: float
    high: float


class Exposure(StrictModel):
    exposed: int
    total: int
    unknown: int = 0


class CaseEffect(StrictModel):
    key: str
    family: str
    means: dict[str, Interval]
    counts: dict[str, int]
    delta: Interval
    saturated: bool


class MemberSeparation(StrictModel):
    effect: Interval
    bound: Interval
    cases: int
    separates: bool
    direction: Literal["benefit", "harm", "unresolved"]


class JudgeQuality(StrictModel):
    """Per judged question, over all graded trials of both arms."""
    trials: int
    unknown: int
    disagreements: int
    compared: int


class Analysis(StrictModel):
    with_arm: str
    without_arm: str
    target: str
    verdict: Literal["keep", "benefit", "equivalent", "harm", "inconclusive", "split"]
    action: str
    effect: Interval
    bound: Interval
    t: Interval | None
    cases: list[CaseEffect]
    unknowns: int
    infra_errors: int
    cost_delta: float | None
    tokens_delta: float | None
    seconds_delta: float | None
    exposure: dict[str, Exposure]
    check_rates: dict[str, dict[str, Interval]]
    pass_k: dict[str, Interval | None]
    reliability_k: int
    saturated: bool
    member_separation: dict[str, MemberSeparation] = Field(default_factory=dict)
    judge_quality: dict[str, JudgeQuality] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def _beta_fraction(a: float, b: float, x: float) -> float:
    """Modified Lentz continued fraction; Numerical Recipes incomplete beta."""
    tiny = 1e-300
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 401):
        delta = 1.0
        for coefficient in (m * (b - m) * x / ((a + 2*m - 1) * (a + 2*m)),
                            -(a + m) * (a + b + m) * x / ((a + 2*m) * (a + 2*m + 1))):
            d = 1 + coefficient * d
            d = d if abs(d) > tiny else tiny
            c = 1 + coefficient / c
            c = c if abs(c) > tiny else tiny
            d = 1 / d
            delta = d * c
            h *= delta
        if abs(delta - 1) < 3e-14:
            return h
    raise ArithmeticError("incomplete beta failed to converge")


def regularized_beta(x: float, a: float, b: float) -> float:
    if not (0 <= x <= 1 and a > 0 and b > 0):
        raise ValueError("invalid incomplete beta arguments")
    if x in (0, 1):
        return x
    factor = math.exp(math.lgamma(a+b) - math.lgamma(a) - math.lgamma(b)
                      + a * math.log(x) + b * math.log1p(-x))
    if x < (a+1)/(a+b+2):
        return factor * _beta_fraction(a, b, x) / a
    return 1 - factor * _beta_fraction(b, a, 1-x) / b


def t_quantile(probability: float, df: int) -> float:
    if not 0 < probability < 1 or df < 1:
        raise ValueError("t quantile requires 0<p<1 and df>=1")
    if probability == 0.5:
        return 0.0
    if probability < 0.5:
        return -t_quantile(1-probability, df)
    lo, hi = 0.0, 1.0

    def cdf(value: float) -> float:
        return 1 - 0.5 * regularized_beta(df / (df + value*value), df/2, 0.5)

    while cdf(hi) < probability:
        hi *= 2
        if not math.isfinite(hi):
            raise ArithmeticError("t quantile failed to bracket")
    for _ in range(100):
        mid = (lo+hi)/2
        if cdf(mid) < probability:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def success(checks: Sequence[GradedCheck]) -> bool | None:
    critical = [c.passed for c in checks if c.critical or c.id == "completion"]
    if False in critical:
        return False
    if not any(c.id == "completion" and c.source == "verifier" for c in checks) or None in critical:
        return None
    return True


def _rate(values: Sequence[bool | None]) -> Interval:
    if not values:
        return Interval(low=0.0, high=1.0)
    return Interval(low=sum(v is True for v in values)/len(values),
                    high=sum(v is not False for v in values)/len(values))


def _pass_k(values: list[bool | None], k: int) -> Interval | None:
    if len(values) < k:
        return None
    denominator = math.comb(len(values), k)
    lower = sum(v is True for v in values)
    upper = sum(v is not False for v in values)
    return Interval(low=math.comb(lower, k)/denominator, high=math.comb(upper, k)/denominator)


def _metric_delta(groups: dict[str, dict[str, list[Observation]]], with_arm: str,
                  without_arm: str, metric: Literal["cost", "tokens", "seconds"]) -> float | None:
    deltas: list[float] = []
    for arms in groups.values():
        values: dict[str, list[float]] = {}
        for arm in [with_arm, without_arm]:
            measurements = [getattr(o, metric) for o in arms[arm]]
            if any(v is None for v in measurements):
                return None
            values[arm] = [float(v) for v in measurements if v is not None]
        deltas.append(mean(values[with_arm]) - mean(values[without_arm]))
    return mean(deltas) if deltas else None


def _member_effects(groups: dict[str, dict[str, list[Observation]]], members: Sequence[str],
                    with_arm: str, without_arm: str) -> dict[str, MemberSeparation]:
    """Targeted-check fractions, averaged trial→case→member; missing is unknown.

    Default check targets are the case targets, including completion. The
    consistent-sign diagnostic triggers decomposition, not a significance claim.
    """
    result: dict[str, MemberSeparation] = {}
    for member in members:
        deltas: list[Interval] = []
        counts: list[tuple[int, int]] = []
        families: list[str] = []
        for arms in groups.values():
            samples: dict[str, list[Interval]] = {with_arm: [], without_arm: []}
            relevant = any(member in (check.targets or obs.targets)
                           for observations in arms.values() for obs in observations for check in obs.checks)
            if not relevant:
                continue
            for arm in [with_arm, without_arm]:
                for obs in arms[arm]:
                    checks = [check.passed for check in obs.checks if member in (check.targets or obs.targets)]
                    samples[arm].append(_rate(checks))
            first, second = samples[with_arm], samples[without_arm]
            deltas.append(Interval(low=mean(v.low for v in first)-mean(v.high for v in second),
                                   high=mean(v.high for v in first)-mean(v.low for v in second)))
            counts.append((len(first), len(second)))
            families.append(arms[with_arm][0].family)
        n = len(deltas)
        effect = Interval(low=mean(d.low for d in deltas) if n else -1.0,
                          high=mean(d.high for d in deltas) if n else 1.0)
        radius = math.sqrt(math.log(2/(ALPHA/2))/2 * sum(
            (1/n)**2/count for pair in counts for count in pair)) if n else 2.0
        bound = Interval(low=max(-1.0, effect.low-radius), high=min(1.0, effect.high+radius))
        balanced = len({c for pair in counts for c in pair}) == 1 and all(c in {3, 6} for pair in counts for c in pair)
        independent = len(set(families)) == n
        positive = effect.low > SEPARATION_THRESHOLD and n >= 2 and all(d.low > 0 for d in deltas)
        negative = effect.high < -SEPARATION_THRESHOLD and n >= 2 and all(d.high < 0 for d in deltas)
        bounded_positive = n >= 6 and balanced and bound.low > 0
        bounded_negative = n >= 6 and balanced and bound.high < 0
        direction: Literal["benefit", "harm", "unresolved"] = "unresolved"
        if independent and (positive or bounded_positive):
            direction = "benefit"
        elif independent and (negative or bounded_negative):
            direction = "harm"
        result[member] = MemberSeparation(effect=effect, bound=bound, cases=n,
                                          separates=direction != "unresolved", direction=direction)
    return result


def analyze(observations: Sequence[Observation], with_arm: str, without_arm: str, *,
            target: str = "all", protected: Sequence[str] = (), costs_context: bool = True,
            members: Sequence[str] = (), final_look: int = 6) -> Analysis:
    if with_arm == without_arm:
        raise ValueError("distinct arms required")
    selected = [o for o in observations if o.arm in {with_arm, without_arm}]
    groups: dict[str, dict[str, list[Observation]]] = defaultdict(lambda: defaultdict(list))
    seen: set[tuple[str, str, int]] = set()
    infra_errors = sum(o.infra_error for o in selected)
    for obs in selected:
        key = (obs.case_key, obs.arm, obs.replicate)
        if key in seen:
            raise ValueError("duplicate case/arm/replicate observation")
        seen.add(key)
        if not obs.infra_error:
            groups[obs.case_key][obs.arm].append(obs)
    warnings: list[str] = []
    paired = {key: arms for key, arms in groups.items() if arms.get(with_arm) and arms.get(without_arm)}
    if len(paired) != len(groups):
        warnings.append("Unpaired cases excluded; panel incomplete.")
    effects: list[CaseEffect] = []
    for key, arms in sorted(paired.items()):
        means = {arm: _rate([success(o.checks) for o in arms[arm]]) for arm in [with_arm, without_arm]}
        families = {o.family for arm in arms.values() for o in arm}
        if len(families) != 1:
            raise ValueError("case family changes across observations")
        effects.append(CaseEffect(key=key, family=next(iter(families)), means=means,
            counts={arm: len(arms[arm]) for arm in [with_arm, without_arm]},
            delta=Interval(low=means[with_arm].low-means[without_arm].high,
                           high=means[with_arm].high-means[without_arm].low),
            saturated=all(v.low == 1 for v in means.values())))
    n = len(effects)
    if n < 6:
        warnings.append("Fewer than 6 paired cases: coverage insufficient; t interval unreliable.")
    family_count = len({c.family for c in effects})
    independent = family_count == n
    if not independent:
        warnings.append("Repeated failure families: cases are not independent coverage units.")
    effect = Interval(low=mean(c.delta.low for c in effects) if n else -1.0,
                      high=mean(c.delta.high for c in effects) if n else 1.0)
    counts = {count for case in effects for count in case.counts.values()}
    balanced = len(counts) == 1 and next(iter(counts), 0) in {3, 6}
    if not balanced:
        warnings.append("Not a complete balanced fixed look (3 or 6 trials/arm/case); no formal verdict.")
    # General weighted form; unequal counts are descriptive only, never authorize a decision.
    radius = math.sqrt(math.log(2/(ALPHA/2))/2 * sum(
        (1/n)**2 / count for case in effects for count in case.counts.values())) if n else 2.0
    bound = Interval(low=max(-1.0, effect.low-radius), high=min(1.0, effect.high+radius))
    unknowns = sum(c.passed is None for o in selected if not o.infra_error for c in o.checks)
    unknown_success = any(success(o.checks) is None for o in selected if not o.infra_error)
    t_interval: Interval | None = None
    if n > 1 and not unknown_success:
        deltas = [case.delta.low for case in effects]
        half = t_quantile(0.975, n-1) * stdev(deltas)/math.sqrt(n)
        t_interval = Interval(low=max(-1.0, mean(deltas)-half), high=min(1.0, mean(deltas)+half))
    if unknowns:
        warnings.append(f"Unknown judgments/checks: {unknowns}; worst/best score bounds retained.")
    if infra_errors:
        warnings.append(f"Infrastructure errors/ungraded trials: {infra_errors}; never counted as agent failures.")
    saturated = sum(case.saturated for case in effects)
    if saturated:
        warnings.append(f"Saturated cases (both arms 100%): {saturated}/{n}.")
    verdict: Literal["keep", "benefit", "equivalent", "harm", "inconclusive", "split"] = "inconclusive"
    confirmed = any(o.confirmed_critical_counterexample for o in selected if o.arm == with_arm and not o.infra_error)
    if confirmed:
        verdict = "harm"
    elif balanced and independent and n >= 6 and not infra_errors and len(paired) == len(groups):
        if bound.low > 0.10:
            verdict = "keep"
        elif bound.low > 0:
            verdict = "benefit"
        elif bound.low > -0.10 and bound.high < 0.10:
            verdict = "equivalent"
        elif bound.high < -0.10:
            verdict = "harm"
    member_separation = _member_effects(paired, members, with_arm, without_arm)
    if len(members) > 1 and verdict in {"equivalent", "inconclusive"} and any(m.separates for m in member_separation.values()):
        verdict = "split"
        warnings.append("Block members separate in targeted checks; split before any deletion (cancellation safeguard).")
    # The whole harness is never deleted on missing evidence: an inconclusive screen
    # only says where to look next.
    protected_target = target in {"all", "user-all"} or any(
        value in protected or ("user-all" if value.startswith("user-") else "all") in protected
        for value in (list(members) or [target]))
    action = {"keep": "keep", "benefit": "keep", "equivalent": "delete", "split": "split",
              "harm": "fix-or-delete", "inconclusive": "keep" if protected_target or not costs_context else "delete-if-costs-context"}[verdict]
    # Resolved balanced looks stop immediately. Only unresolved comparisons
    # spend the remaining look; final_look freezes the policy boundary.
    panel_complete = bool(selected) and len(paired) == len(groups)
    final_complete = balanced and counts == {final_look}
    if not confirmed:
        ungraded = any(not o.checks for o in selected if not o.infra_error)
        if infra_errors or ungraded:
            if ungraded:
                warnings.append("Ungraded trials; grade them (`analyze --project`) before deciding.")
            action = "retry"
        elif verdict != "split":
            if not panel_complete or not balanced:
                action = "next-look"
            elif family_count < 6 or not independent:
                action = "add-cases" if final_complete else "next-look"
            elif verdict == "inconclusive" and not final_complete:
                action = "next-look"
    exposure: dict[str, Exposure] = {}
    pass_k: dict[str, Interval | None] = {}
    for arm in [with_arm, without_arm]:
        arm_obs = [o for o in selected if o.arm == arm and not o.infra_error]
        exposure[arm] = Exposure(exposed=sum(o.exposed is True for o in arm_obs), total=len(arm_obs),
                                 unknown=sum(o.exposed is None for o in arm_obs))
        if arm == with_arm and arm_obs and not exposure[arm].exposed and not exposure[arm].unknown:
            warnings.append(f"Target never loaded ({arm}: 0/{len(arm_obs)}): its trigger is broken or these "
                            "cases do not exercise it. Check the trigger before content decisions.")
        reliability = [_pass_k([success(o.checks) for o in arms[arm]], RELIABILITY_K) for arms in paired.values()]
        pass_k[arm] = (Interval(low=mean(v.low for v in reliability if v is not None),
                               high=mean(v.high for v in reliability if v is not None))
                       if reliability and all(v is not None for v in reliability) else None)
    if (not confirmed and not infra_errors and exposure[with_arm].total
            and exposure[with_arm].exposed == 0 and exposure[with_arm].unknown == 0):
        verdict, action = "inconclusive", "fix-trigger"
    elif (not confirmed and action in {"delete", "delete-if-costs-context", "fix-or-delete"}
          and (not exposure[with_arm].exposed or exposure[with_arm].unknown)):
        verdict, action = "inconclusive", "fix-trigger"
        warnings.append("Exposure incomplete in with arm; diagnose trigger before deletion.")
    check_values: dict[str, dict[str, list[bool | None]]] = defaultdict(lambda: defaultdict(list))
    sources: dict[str, set[str]] = defaultdict(set)
    check_keys = {(check.source, check.id) for obs in selected for check in obs.checks}
    for source, check_id in check_keys:
        sources[check_id].add(source)
    for obs in selected:
        if not obs.infra_error:
            present = {(check.source, check.id): check.passed for check in obs.checks}
            for source, check_id in check_keys:
                key = check_id if len(sources[check_id]) == 1 else f"{source}:{check_id}"
                check_values[key][obs.arm].append(present.get((source, check_id)))
    check_rates = {key: {arm: _rate(arms.get(arm, [])) for arm in [with_arm, without_arm]}
                   for key, arms in sorted(check_values.items())}
    judge_quality: dict[str, JudgeQuality] = {}
    for question in sorted({check.id for obs in selected for check in obs.checks if check.source == "judge"}):
        judged = [check for obs in selected if not obs.infra_error
                  for check in obs.checks if check.source == "judge" and check.id == question]
        compared = [check for check in judged if check.disagreement is not None]
        judge_quality[question] = JudgeQuality(trials=len(judged), unknown=sum(c.passed is None for c in judged),
            disagreements=sum(bool(c.disagreement) for c in compared), compared=len(compared))
    return Analysis(with_arm=with_arm, without_arm=without_arm, target=target, verdict=verdict, action=action,
        effect=effect, bound=bound, t=t_interval, cases=effects, unknowns=unknowns, infra_errors=infra_errors,
        cost_delta=_metric_delta(paired, with_arm, without_arm, "cost"),
        tokens_delta=_metric_delta(paired, with_arm, without_arm, "tokens"),
        seconds_delta=_metric_delta(paired, with_arm, without_arm, "seconds"),
        exposure=exposure, check_rates=check_rates, pass_k=pass_k, reliability_k=RELIABILITY_K,
        saturated=bool(effects) and saturated == n, warnings=warnings,
        member_separation=member_separation, judge_quality=judge_quality)
