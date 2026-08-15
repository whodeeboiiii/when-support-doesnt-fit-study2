"""SQLAlchemy 선언적 기반 (구현명세서 §8.1).

불변 규칙(v5.0 §2.4.2 승계): 어떤 모델도 `schema=`를 갖지 않는다. schema(`proto_v1` →
`main_v1`)는 오직 연결 수준의 search_path에서만 결정된다 — `models/session.py` 참조.
DEV_MODE의 SQLite에는 schema 개념이 없으므로 이 규칙 덕분에 같은 모델 정의가 양쪽에서 돈다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

#: §8.1의 jsonb 컬럼. Postgres에서는 JSONB, SQLite(DEV_MODE)에서는 JSON으로 내려간다.
JsonB = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """§8.1의 `id`. Postgres는 UUID, SQLite는 CHAR(32)로 내려간다."""
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
