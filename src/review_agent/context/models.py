"""ReviewContext and its parts (dataclasses -- deterministic, ``asdict``-friendly).

Ported from ``coderepo/ContextPrep/context_creator.ipynb`` cell 6.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Hunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: List[str]  # raw diff body lines incl. leading ' ' '+' '-'


@dataclass
class FileChange:
    file: str
    status: str  # added | modified | deleted | renamed
    language: str = ""
    old_path: Optional[str] = None
    hunks: List[Hunk] = field(default_factory=list)


@dataclass
class CodeSlice:
    file: str
    reason: str  # enclosing | referenced | test
    symbol: str
    content: str
    tokens: int


@dataclass
class KnowledgeDoc:
    path: str
    selector: str  # always | glob | schema
    content: str
    tokens: int


@dataclass
class CommentItem:
    file: Optional[str]
    line: Optional[int]
    author: str
    is_ai: bool
    resolved: bool
    body: str


@dataclass
class PRInfo:
    id: Optional[int]
    title: str
    description: str
    source_branch: str
    target_branch: str
    commit_messages: List[str] = field(default_factory=list)


@dataclass
class ReviewContext:
    pr: PRInfo
    changes: List[FileChange] = field(default_factory=list)
    code: List[CodeSlice] = field(default_factory=list)
    knowledge: List[KnowledgeDoc] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    comments: List[CommentItem] = field(default_factory=list)
    budget: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pr": asdict(self.pr),
            "changes": [asdict(c) for c in self.changes],
            "code": [asdict(c) for c in self.code],
            "knowledge": [asdict(k) for k in self.knowledge],
            "rules": list(self.rules),
            "comments": [asdict(c) for c in self.comments],
            "budget": self.budget,
        }
