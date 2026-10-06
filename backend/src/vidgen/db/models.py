"""Database schema v1: generation jobs and the media assets they produce."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobMode(enum.StrEnum):
    T2V = "t2v"
    I2V = "i2v"


class AssetKind(enum.StrEnum):
    VIDEO = "video"
    THUMBNAIL = "thumbnail"
    INPUT_IMAGE = "input_image"


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # Store the lowercase values, not the Python member names.
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.QUEUED
    )
    mode: Mapped[JobMode] = mapped_column(_enum(JobMode, "job_mode"))
    engine: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(Text)
    # Generation parameters (resolution, frames, steps, seed, ...), validated by the API.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_jobs_created_at", "created_at"),
        Index("ix_jobs_status", "status"),
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    kind: Mapped[AssetKind] = mapped_column(_enum(AssetKind, "asset_kind"))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # e.g. width, height, fps, frame count, duration.
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="assets")

    __table_args__ = (Index("ix_assets_job_id", "job_id"),)
