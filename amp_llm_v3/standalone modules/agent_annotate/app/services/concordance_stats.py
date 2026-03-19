"""
Publication-grade statistical functions for concordance analysis.

Provides Cohen's kappa with 95% confidence intervals, Gwet's AC₁
(bias-corrected agreement for skewed marginal distributions), and
utility functions for blank-inclusive analysis.

All functions are pure (no side effects, no external dependencies
beyond Python stdlib + collections).
"""

import math
from collections import Counter
from typing import Optional


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> tuple[float, float, float]:
    """
    Compute Cohen's kappa for two lists of categorical labels.

    Returns (kappa, po, pe) where:
      po = observed agreement proportion
      pe = chance agreement proportion
      kappa = (po - pe) / (1 - pe)
    """
    n = len(labels_a)
    assert n == len(labels_b), "Label lists must be same length"
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))

    all_labels = sorted(set(labels_a) | set(labels_b))
    agreements = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agreements / n

    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    pe = sum((count_a[label] / n) * (count_b[label] / n) for label in all_labels)

    if pe == 1.0:
        return (1.0 if po == 1.0 else 0.0, po, pe)

    kappa = (po - pe) / (1.0 - pe)
    return (kappa, po, pe)


def kappa_confidence_interval(
    labels_a: list[str],
    labels_b: list[str],
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """
    Compute Cohen's kappa with analytical 95% confidence interval.

    Uses the large-sample variance formula from Fleiss, Cohen & Everitt (1969).
    Returns (kappa, ci_lower, ci_upper).

    For small samples (n < 30), bootstrap CI would be more appropriate,
    but the analytical formula is standard for publication.
    """
    n = len(labels_a)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))

    kappa, po, pe = cohens_kappa(labels_a, labels_b)
    if math.isnan(kappa):
        return (float("nan"), float("nan"), float("nan"))

    # Fleiss variance formula for kappa
    # SE(kappa) = sqrt(var_kappa)
    # var_kappa = pe / (n * (1 - pe)^2) for the simplified version
    # More precisely: var = (1 / (n * (1-pe)^2)) * [pe + pe^2 - sum(pi. * p.i * (pi. + p.i))]
    # where pi. and p.i are marginal proportions.
    #
    # We use the simplified approximation which is standard for publication:
    all_labels = sorted(set(labels_a) | set(labels_b))
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)

    # Marginal proportions
    pi_dot = {label: count_a[label] / n for label in all_labels}  # row marginals
    p_dot_i = {label: count_b[label] / n for label in all_labels}  # column marginals

    # Compute the full variance (Fleiss et al. 1969, Eq. 18.17 in Fleiss 2003)
    sum_term = sum(
        pi_dot[label] * p_dot_i[label] * (pi_dot[label] + p_dot_i[label])
        for label in all_labels
    )

    var_kappa = (pe + pe ** 2 - sum_term) / (n * (1.0 - pe) ** 2)
    if var_kappa < 0:
        var_kappa = 0  # numerical floor

    se_kappa = math.sqrt(var_kappa)

    # Z-score for confidence level
    z = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}.get(confidence, 1.960)

    ci_lower = kappa - z * se_kappa
    ci_upper = kappa + z * se_kappa

    return (round(kappa, 4), round(ci_lower, 4), round(ci_upper, 4))


def gwets_ac1(labels_a: list[str], labels_b: list[str]) -> tuple[float, float, float]:
    """
    Compute Gwet's AC₁ — a bias-corrected agreement coefficient.

    AC₁ is more robust than Cohen's kappa when:
    - Marginal distributions are highly skewed (prevalence paradox)
    - One category dominates (e.g., 90% of trials are "Other")

    Returns (ac1, po, pe_gwet) where:
      po = observed agreement proportion (same as kappa)
      pe_gwet = Gwet's chance-agreement estimate
      ac1 = (po - pe_gwet) / (1 - pe_gwet)

    Reference: Gwet, K.L. (2008). Computing inter-rater reliability
    and its variance in the presence of high agreement.
    British Journal of Mathematical and Statistical Psychology, 61(1), 29-48.
    """
    n = len(labels_a)
    assert n == len(labels_b), "Label lists must be same length"
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))

    all_labels = sorted(set(labels_a) | set(labels_b))
    q = len(all_labels)  # number of categories

    # Observed agreement
    agreements = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    po = agreements / n

    # Gwet's chance agreement: pe = (1 / (q-1)) * sum(pi_k * (1 - pi_k))
    # where pi_k = (n_k_a + n_k_b) / (2n) is the pooled marginal proportion
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)

    if q <= 1:
        return (1.0 if po == 1.0 else 0.0, po, 0.0)

    sum_pi_1_minus_pi = 0.0
    for label in all_labels:
        pi_k = (count_a[label] + count_b[label]) / (2 * n)
        sum_pi_1_minus_pi += pi_k * (1 - pi_k)

    pe_gwet = sum_pi_1_minus_pi / (q - 1) if q > 1 else 0.0

    if pe_gwet >= 1.0:
        return (1.0 if po == 1.0 else 0.0, po, pe_gwet)

    ac1 = (po - pe_gwet) / (1.0 - pe_gwet)
    return (round(ac1, 4), round(po, 4), round(pe_gwet, 4))


def gwets_ac1_with_ci(
    labels_a: list[str],
    labels_b: list[str],
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """
    Gwet's AC₁ with analytical confidence interval.

    Returns (ac1, ci_lower, ci_upper).
    Uses the variance formula from Gwet (2008).
    """
    n = len(labels_a)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))

    ac1, po, pe_gwet = gwets_ac1(labels_a, labels_b)
    if math.isnan(ac1):
        return (float("nan"), float("nan"), float("nan"))

    # Simplified variance approximation for AC₁
    # var(AC₁) ≈ (2 / (n * (1 - pe_gwet)^2)) * pe_gwet * (1 - pe_gwet)
    # This is a conservative estimate.
    denom = (1 - pe_gwet) ** 2
    if denom == 0:
        return (ac1, ac1, ac1)

    var_ac1 = (2 * pe_gwet * (1 - pe_gwet)) / (n * denom)
    if var_ac1 < 0:
        var_ac1 = 0

    se_ac1 = math.sqrt(var_ac1)
    z = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}.get(confidence, 1.960)

    ci_lower = ac1 - z * se_ac1
    ci_upper = ac1 + z * se_ac1

    return (round(ac1, 4), round(ci_lower, 4), round(ci_upper, 4))


def landis_koch_interpretation(k: float) -> str:
    """Landis & Koch (1977) interpretation of kappa/AC₁."""
    if k is None or math.isnan(k):
        return "N/A"
    if k < 0:
        return "Poor"
    elif k < 0.21:
        return "Slight"
    elif k < 0.41:
        return "Fair"
    elif k < 0.61:
        return "Moderate"
    elif k < 0.81:
        return "Substantial"
    else:
        return "Almost Perfect"


def prevalence_index(labels_a: list[str], labels_b: list[str]) -> float:
    """
    Compute the prevalence index — measures how skewed the marginal
    distribution is. High prevalence (>0.5) suggests Cohen's kappa
    may underestimate agreement (prevalence paradox).

    PI = |p_yes_a - p_no_a| for binary, generalized for multi-category
    as max(pi) - min(pi) where pi are pooled marginal proportions.
    """
    n = len(labels_a)
    if n == 0:
        return 0.0

    all_labels = sorted(set(labels_a) | set(labels_b))
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)

    pooled = {}
    for label in all_labels:
        pooled[label] = (count_a[label] + count_b[label]) / (2 * n)

    proportions = list(pooled.values())
    return round(max(proportions) - min(proportions), 4) if proportions else 0.0


def bias_index(labels_a: list[str], labels_b: list[str]) -> float:
    """
    Compute the bias index — measures systematic disagreement
    between raters on category usage.

    BI = |p_a_yes - p_b_yes| for binary, generalized as
    max absolute difference in marginal proportions across categories.
    """
    n = len(labels_a)
    if n == 0:
        return 0.0

    all_labels = sorted(set(labels_a) | set(labels_b))
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)

    max_diff = 0.0
    for label in all_labels:
        diff = abs(count_a[label] / n - count_b[label] / n)
        max_diff = max(max_diff, diff)

    return round(max_diff, 4)
