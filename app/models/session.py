import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="created")
    source_language: Mapped[str] = mapped_column(String(16), default="en")
    target_language: Mapped[str] = mapped_column(String(16), default="hi")
    default_tone: Mapped[str] = mapped_column(String(50), default="neutral-professional")
    raw_audio_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sequence_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SegmentRecord(Base):
    __tablename__ = "segments"
    __table_args__ = (
        Index("ix_segments_session_id_status", "session_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, index=True)
    sequence_start: Mapped[int] = mapped_column(Integer)
    sequence_end: Mapped[int] = mapped_column(Integer)
    audio_start_ms: Mapped[int] = mapped_column(Integer)
    audio_end_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="created")
    processing_state: Mapped[str] = mapped_column(String(50), default="pending")
    audio_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SegmentArtifact(Base):
    __tablename__ = "segment_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50))
    artifact_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SegmentStageRun(Base):
    __tablename__ = "segment_stage_runs"
    __table_args__ = (
        Index("ix_stage_runs_segment_stage_status", "segment_id", "stage_name", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id"), index=True
    )
    stage_name: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="created")
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), index=True
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    sequence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ProtectedTerm(Base):
    __tablename__ = "protected_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term: Mapped[str] = mapped_column(String(255), unique=True)
    term_type: Mapped[str] = mapped_column(String(50), default="brand")
    preserve_as_is: Mapped[bool] = mapped_column(default=True)
    target_rendering: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

