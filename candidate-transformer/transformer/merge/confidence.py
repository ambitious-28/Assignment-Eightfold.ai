"""
Stage 6 — Confidence scoring for arbitrated fields.

Formula (PRD §5.3):
  confidence = base(winner_source) + 0.05 * (agreeing_sources - 1) - (0.10 if conflicted else 0)
  confidence = clamp(confidence, 0.0, 1.0)
  if confidence < 0.40: drop → None + warning

Where:
  base(source)      = SOURCE_TIERS[source]
  agreeing_sources  = count of contributions where agreed=True (winner always counts as at least 1)
  conflicted        = ArbitrationResult.conflicted

Special handling:
  skills            — each SkillEntry scored individually; NOT threshold-gated at field level
  experience/edu    — base(winner_source) only (agreeing=1, conflicted=False)
  overall_confidence — weighted mean; IDENTITY_FIELDS at 2×, others 1×; rounded to 2dp
"""

from __future__ import annotations

from transformer.merge.arbitrate import ArbitrationResult
from transformer.models import (
    IDENTITY_FIELDS,
    SOURCE_TIERS,
    SkillEntry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 0.40

# Fields where we use base(winner_source) only — no agreement/conflict adjustment.
_UNION_STRUCTURAL_FIELDS = frozenset({"experience", "education"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base(source: str) -> float:
    return SOURCE_TIERS.get(source, 0.0)


def _best_tier(sources: list[str]) -> float:
    """Return the highest SOURCE_TIERS score among the given source names."""
    return max((_base(s) for s in sources), default=0.0)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _apply_formula(base: float, agreeing: int, conflicted: bool) -> float:
    raw = base + 0.05 * (agreeing - 1) - (0.10 if conflicted else 0.0)
    return _clamp(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_field(result: ArbitrationResult) -> float | None:
    """
    Compute confidence for one arbitrated scalar/array field.

    Returns a float in [0.40, 1.0], or None if confidence is below threshold
    (caller should treat the field value as dropped / null).
    """
    base = _base(result.winner_source)
    agreeing = sum(1 for c in result.contributions if c.agreed)
    agreeing = max(agreeing, 1)  # winner itself always counts
    confidence = _apply_formula(base, agreeing, result.conflicted)
    if confidence < CONFIDENCE_THRESHOLD:
        return None
    return confidence


def score_skill(skill: SkillEntry) -> float:
    """
    Per-skill confidence using the same formula.

    base       = tier of the best (highest-scoring) source in skill.sources
    agreeing   = len(skill.sources)  (every source listing this skill agrees it exists)
    conflicted = False (skills are unioned, never conflicted)

    Clamped to [0.0, 1.0]. NOT threshold-gated — a skill present in any source is kept.
    """
    base = _best_tier(skill.sources) if skill.sources else 0.0
    agreeing = max(len(skill.sources), 1)
    return _apply_formula(base, agreeing, conflicted=False)


def compute_overall_confidence(
    field_scores: dict[str, float | None],
    identity_weight: float = 2.0,
) -> float:
    """
    Weighted mean of non-None field confidences.

    IDENTITY_FIELDS (full_name, emails, phones) get identity_weight (default 2×);
    all other fields get 1×.

    Dropped fields (None) are excluded from the mean entirely.
    Returns 0.0 if no fields have a score.
    Result is rounded to exactly 2 decimal places.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for field, score in field_scores.items():
        if score is None:
            continue
        w = identity_weight if field in IDENTITY_FIELDS else 1.0
        weighted_sum += score * w
        total_weight += w
    if total_weight == 0.0:
        return 0.0
    return round(weighted_sum / total_weight, 2)


def score_arbitration(
    arbitration: dict[str, ArbitrationResult],
) -> tuple[dict[str, float | None], list[str]]:
    """
    Score all fields from an arbitration result dict.

    Returns:
        field_scores  — field_name → float confidence, or None if dropped
        drop_warnings — one human-readable warning string per dropped field
    """
    field_scores: dict[str, float | None] = {}
    drop_warnings: list[str] = []

    for field, result in arbitration.items():
        if field in _UNION_STRUCTURAL_FIELDS:
            # experience / education: base only, no agreement/conflict adjustment
            confidence = _clamp(_base(result.winner_source))
            if confidence < CONFIDENCE_THRESHOLD:
                field_scores[field] = None
                drop_warnings.append(
                    f"{field}: confidence {confidence:.2f} below threshold, dropped"
                )
            else:
                field_scores[field] = confidence

        elif field == "skills":
            # Skills: score each SkillEntry individually; field score = mean
            skill_entries: list[SkillEntry] = result.winner_value or []
            if not skill_entries:
                field_scores[field] = None
            else:
                scores = [score_skill(s) for s in skill_entries]
                field_scores[field] = round(sum(scores) / len(scores), 4)
                # Skills are never threshold-gated at the field level

        else:
            # Standard formula for all other fields
            confidence = score_field(result)
            field_scores[field] = confidence
            if confidence is None:
                if result.method == "normalization_failed":
                    # All sources attempted this field but every value failed to
                    # normalize (e.g. yearsExp="lots"). Report root cause directly.
                    drop_warnings.append(
                        f"{field}: all sources failed normalization, value set to null"
                    )
                else:
                    # Compute the actual raw confidence value for the warning message.
                    base = _base(result.winner_source)
                    agreeing = max(sum(1 for c in result.contributions if c.agreed), 1)
                    raw = _clamp(base + 0.05 * (agreeing - 1) - (0.10 if result.conflicted else 0.0))
                    drop_warnings.append(
                        f"{field}: confidence {raw:.2f} below threshold, dropped"
                    )
            elif result.conflicted:
                # Conflict detected but confidence is above threshold — winner is
                # retained.  Record the conflict in warnings so downstream reviewers
                # know the field had disagreeing sources.
                if field in ("emails", "phones"):
                    # Union field: all values are kept; the "conflict" is that the
                    # sources gave different addresses/numbers.
                    drop_warnings.append(
                        f"{field}: sources disagree — all values unioned, "
                        f"review recommended"
                    )
                else:
                    # Scalar field: the highest-tier source wins; other values are
                    # discarded.  e.g. full_name "Vivaan Reddy" vs "V. Reddy".
                    drop_warnings.append(
                        f"{field}: conflict between sources — "
                        f"winner from {result.winner_source!r} kept"
                    )

    return field_scores, drop_warnings
