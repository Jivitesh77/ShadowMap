"""Database tables (blueprint §18 "What is stored"). All times are UTC."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


class Street(Base):
    """One stretch of street between two junctions (an edge of the routing graph)."""

    __tablename__ = "streets"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_way_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    road_type: Mapped[str] = mapped_column(String(50))  # OSM highway tag, e.g. primary, residential, footway
    start_node: Mapped[int] = mapped_column(Integer, index=True)  # OSM node id
    end_node: Mapped[int] = mapped_column(Integer, index=True)
    length_m: Mapped[float] = mapped_column(Float)
    geometry: Mapped[list] = mapped_column(JSON)  # [[lat, lon], ...]
    map_score: Mapped[float | None] = mapped_column(Float)

    observations: Mapped[list["Observation"]] = relationship(back_populates="street")
    reports: Mapped[list["Report"]] = relationship(back_populates="street")


class Place(Base):
    """A safe place a person could walk into (blueprint §4)."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[str | None] = mapped_column(String(40), unique=True)  # e.g. "node/123"
    name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    opening_hours: Mapped[str | None] = mapped_column(String(300))  # raw OSM text
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(50), default="openstreetmap")
    last_seen_open_at: Mapped[datetime | None] = mapped_column(DateTime)


class Observation(Base):
    """One analysed Sentinel photo or video frame (blueprint §6)."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    street_id: Mapped[int | None] = mapped_column(ForeignKey("streets.id"), index=True)
    sentinel_label: Mapped[str] = mapped_column(String(80))  # e.g. "Zomato Rider #01"
    source: Mapped[str] = mapped_column(String(20))  # "live" or "video"
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)

    # Filled by the AI. Null until analysed.
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / done / unclear / failed
    lighting: Mapped[str | None] = mapped_column(String(10))  # bright / dim / dark
    streetlights_visible: Mapped[int | None] = mapped_column(Integer)
    streetlights_working: Mapped[int | None] = mapped_column(Integer)
    people: Mapped[str | None] = mapped_column(String(10))  # none / few / many
    open_places_count: Mapped[int | None] = mapped_column(Integer)
    open_places_types: Mapped[list | None] = mapped_column(JSON)
    vehicles: Mapped[str | None] = mapped_column(String(10))  # none / some / busy
    isolation: Mapped[str | None] = mapped_column(String(20))  # open road / lane / underpass / empty plot / market
    hazards: Mapped[list | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(10))  # low / medium / high
    photo_score: Mapped[float | None] = mapped_column(Float)

    photo_path: Mapped[str | None] = mapped_column(String(300))  # cleared when the photo is deleted
    photo_delete_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    street: Mapped[Street | None] = relationship(back_populates="observations")


class Report(Base):
    """A one-tap community report (blueprint §10). No free text, by design."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    street_id: Mapped[int | None] = mapped_column(ForeignKey("streets.id"), index=True)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"))
    kind: Mapped[str] = mapped_column(String(30))  # broken_light / dark / deserted / felt_unsafe / well_lit / place_closed / place_open
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    device_id: Mapped[str | None] = mapped_column(String(64))  # anonymous id, for rate limiting only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fades_at: Mapped[datetime | None] = mapped_column(DateTime)

    street: Mapped[Street | None] = relationship(back_populates="reports")


class Walk(Base):
    """A Walk With Me trip (blueprint §9)."""

    __tablename__ = "walks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # random id used in the trip link
    walker_name: Mapped[str] = mapped_column(String(80))
    walker_phone: Mapped[str | None] = mapped_column(String(30))
    route: Mapped[list] = mapped_column(JSON)  # [[lat, lon], ...]
    dest_lat: Mapped[float] = mapped_column(Float)
    dest_lon: Mapped[float] = mapped_column(Float)
    pin_hash: Mapped[str] = mapped_column(String(200))
    duress_pin_hash: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / checking / alert / arrived / ended
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expected_arrival_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    last_position_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_moved_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="walk", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="walk", cascade="all, delete-orphan")


class Contact(Base):
    """A trusted contact for one walk (up to 3)."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    walk_id: Mapped[str] = mapped_column(ForeignKey("walks.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(30))

    walk: Mapped[Walk] = relationship(back_populates="contacts")


class Alert(Base):
    """One step of the escalation ladder (blueprint §9, §11)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    walk_id: Mapped[str] = mapped_column(ForeignKey("walks.id"), index=True)
    level: Mapped[str] = mapped_column(String(20))  # ask / contacts / police
    trigger: Mapped[str] = mapped_column(String(20))  # stopped / off_route / late / sos / duress / battery
    status: Mapped[str] = mapped_column(String(20), default="new")  # new / acknowledged / unit_sent / resolved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    walk: Mapped[Walk] = relationship(back_populates="alerts")
