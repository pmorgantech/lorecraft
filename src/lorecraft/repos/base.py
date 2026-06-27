"""Shared repository primitives."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlmodel import SQLModel, Session, select

ModelT = TypeVar("ModelT", bound=SQLModel)
KeyT = TypeVar("KeyT", bound=object)


class Repository(Generic[ModelT, KeyT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get(self, id_: KeyT) -> ModelT | None:
        return self.session.get(self.model, id_)

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)

    def list_all(
        self, *, offset: int = 0, limit: int | None = None
    ) -> Sequence[ModelT]:
        statement = select(self.model).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.exec(statement).all()
