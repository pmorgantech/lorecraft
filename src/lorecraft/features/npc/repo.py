"""Dialogue tree data access."""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.features.npc.models import DialogueTree
from lorecraft.engine.repos.base import Repository


class DialogueRepo(Repository[DialogueTree, str]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DialogueTree)
