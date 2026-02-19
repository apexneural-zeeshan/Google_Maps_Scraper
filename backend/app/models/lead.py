import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id"),
        nullable=False,
        index=True,
    )
    place_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    # Business info
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    types: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rich data
    opening_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    photos: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reviews_per_score: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Contact & enrichment data
    primary_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    emails: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    social_links: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    employee_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year_established: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(
        String(20), default="places_api", nullable=False
    )
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="leads")

    __table_args__ = (
        Index("ix_leads_job_id_place_id", "job_id", "place_id", unique=True),
        Index("ix_leads_name", "name"),
        Index("ix_leads_rating", "rating"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<Lead {self.place_id} {self.name}>"
