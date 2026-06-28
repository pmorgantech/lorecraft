"""Dialogue tree data access."""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.models.dialogue import DialogueTree
from lorecraft.repos.base import Repository


class DialogueRepo(Repository[DialogueTree, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DialogueTree)
