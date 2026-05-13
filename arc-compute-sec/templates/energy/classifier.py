"""Energy subclassifier.

DRIFT from prior TASK.md: this classifier was supposed to compose with an
upstream category classifier (`finance_macro`, etc.). The upstream relayer
has no callable categorizer — categories are data-baked in the master TSV
only. So this is the STANDALONE classifier: single-gate on keyword match
across title + description.

Returns one of the template_ids in `keywords.yaml`, or None. Conservative:
prefers None over a false-positive match.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_KW_PATH = Path(__file__).parent / "keywords.yaml"
_REGEX_META = re.compile(r"[.\\*+?\[\]()|^$]")


@lru_cache(maxsize=1)
def _load_keywords() -> dict[str, list[str]]:
    return yaml.safe_load(_KW_PATH.read_text())


def classify_energy(
    title: str,
    description: str = "",
    upstream_category: str | None = None,  # kept for API compat; ignored (single-gate)
) -> str | None:
    """Return energy_template_id or None.

    The single keyword gate must match somewhere in title + description.
    The `upstream_category` parameter is accepted but ignored; documented in
    TASK.md drift table delta D3.
    """
    blob = f"{title or ''}\n{description or ''}".lower()
    for template_id, patterns in _load_keywords().items():
        for p in patterns:
            if _REGEX_META.search(p):
                if re.search(p, blob, re.IGNORECASE):
                    return template_id
            else:
                if p.lower() in blob:
                    return template_id
    return None
