"""``review-rules.yaml`` -> flat list of invariant strings, passed verbatim to the model.

Ported from ``context_creator.ipynb`` cell 20. Deliberately a tiny hand parser -- the
file is a flat YAML list of strings, nothing more.
"""

from __future__ import annotations

from typing import List


def load_rules(repo, cfg) -> List[str]:
    text = repo.read(cfg.rules_file)
    if not text:
        return []
    rules: List[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- "):
            rules.append(s[2:].strip().strip("\"'"))
        elif s.startswith("-"):
            rules.append(s[1:].strip().strip("\"'"))
    return rules
