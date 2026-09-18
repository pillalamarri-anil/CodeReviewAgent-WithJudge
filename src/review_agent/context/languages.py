"""Extension -> language classification. Ported from ``context_creator.ipynb`` cell 12."""

from __future__ import annotations

import os
from typing import List

from .models import FileChange

_EXT_LANG = {
    ".java": "java", ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".kt": "kotlin", ".go": "go", ".rb": "ruby",
    ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cs": "csharp",
    ".php": "php", ".scala": "scala", ".sql": "sql", ".md": "markdown", ".yaml": "yaml",
    ".yml": "yaml", ".xml": "xml", ".json": "json", ".properties": "properties",
    ".gradle": "gradle", ".sh": "shell", ".html": "html", ".css": "css",
}


def detect_language(path: str) -> str:
    if os.path.basename(path).lower() == "dockerfile":
        return "dockerfile"
    return _EXT_LANG.get(os.path.splitext(path.lower())[1], "text")


def annotate_languages(changes: List[FileChange]) -> List[FileChange]:
    for c in changes:
        c.language = detect_language(c.file)
    return changes
