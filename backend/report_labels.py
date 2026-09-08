"""
report_labels.py
-----------------
The shared reporting vocabulary used by more than one output generator:
the Available/Unavailable status wording and the cell-fill colors for the
Item-Tail badge and that status.

Kept in one place so the Seller ATP DKPC (DKPC-level) and Item-Tail
(DKP-level) exports can never drift into different wording or different
colors for the same concept.
"""
from __future__ import annotations

from typing import Final

from .config import TailClassification

STATUS_COLUMN: Final[str] = "Status"
STATUS_AVAILABLE: Final[str] = "Available"
STATUS_UNAVAILABLE: Final[str] = "Unavailable"

TAIL_BADGE_COLUMN: Final[str] = "Tail Badge"

# Red/yellow/green, matching the color scales used everywhere else.
TAIL_BADGE_COLORS: Final[dict[str, str]] = {
    TailClassification.ST: "63BE7B",  # green
    TailClassification.MT: "FFEB84",  # yellow
    TailClassification.LT: "F8696B",  # red
}
STATUS_COLORS: Final[dict[str, str]] = {
    STATUS_AVAILABLE: "63BE7B",  # green
    STATUS_UNAVAILABLE: "F8696B",  # red
}

# Sort priority for the badge — ST (a seller's own best sellers) first, so
# the rows that matter most sit at the top of a report.
TAIL_BADGE_SORT_RANK: Final[dict[str, int]] = {
    badge: rank for rank, badge in enumerate(TailClassification.ALL)
}
