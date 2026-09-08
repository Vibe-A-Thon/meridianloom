"""Greenfield/brownfield classification (FR-M37-06; F0 Workstream F task 29).

The rule (documented here because the spec leaves the defaults to the
implementation, and every trust metric must report this split per G6):

A story's or session's changes — given as a commit list or a base..compare
range — are **greenfield** when either

* the new-file ratio (files added / files added + modified or deleted) is
  >= ``new_file_ratio_threshold`` (default 0.5, the
  ``meridian.greenfieldNewFileRatio`` workspace setting), OR
* the median age of the touched code is < ``max_median_age_days`` (default
  30, the ``meridian.greenfieldMaxMedianAgeDays`` workspace setting).

Touched-code age is per line and deterministic from git: a line an
existing file loses in a story commit was introduced by whatever commit
blame at that commit's parent says; its age is the story commit's date
minus the introducing commit's date. The median runs over the code the
story *changed that existed before it* — a story that only adds files has
no pre-existing touched code, the age limb stays silent (null) and the
ratio limb decides. A story editing five-year-old code with no new files
is brownfield on both limbs; a purely additive story on month-old code is
greenfield on the ratio limb alone. Nothing here is a model judgement
(FR-M36-07).
"""

from .greenfield import (
    DEFAULT_MAX_MEDIAN_AGE_DAYS,
    DEFAULT_NEW_FILE_RATIO_THRESHOLD,
    BROWNFIELD,
    GREENFIELD,
    Classification,
    classify,
)
from .compare import compute_agent_comparison
from .dora import compute_dora_metrics, export_otlp
from .jcurve import compute_jcurve, parse_utc
from .reasons import compute_reason_distribution, detection_shape
from .score import SCORE_WEIGHTS, compute_trust_score
from .spend import (
    DEFAULT_MIN_PERIODS,
    DEFAULT_SPEND_RISE_THRESHOLD,
    SpendPoint,
    SpendSeries,
    YieldPoint,
    detect_tokenmaxxing,
)
from .trust import TrustMetricsCache, compute_rejection_rate

__all__ = [
    "BROWNFIELD",
    "Classification",
    "DEFAULT_MAX_MEDIAN_AGE_DAYS",
    "DEFAULT_MIN_PERIODS",
    "DEFAULT_NEW_FILE_RATIO_THRESHOLD",
    "DEFAULT_SPEND_RISE_THRESHOLD",
    "GREENFIELD",
    "SCORE_WEIGHTS",
    "SpendPoint",
    "SpendSeries",
    "TrustMetricsCache",
    "YieldPoint",
    "classify",
    "compute_agent_comparison",
    "compute_dora_metrics",
    "compute_jcurve",
    "compute_reason_distribution",
    "compute_rejection_rate",
    "compute_trust_score",
    "detect_tokenmaxxing",
    "detection_shape",
    "export_otlp",
    "parse_utc",
]
