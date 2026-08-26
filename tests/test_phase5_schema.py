from __future__ import annotations

from collections import Counter

from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint

from rag_platform.application.db.models import Base


def test_postgresql_relation_like_names_are_unique() -> None:
    names = [table.name for table in Base.metadata.tables.values()]
    names.extend(
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name
    )
    names.extend(
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint)) and constraint.name
    )

    duplicates = {name: count for name, count in Counter(names).items() if count > 1}

    assert duplicates == {}
