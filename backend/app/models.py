"""Database tables (blueprint §18 "What is stored"). All times are UTC."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


def _default_city() -> str:
    from app.services.cities import default_city  # rows created without a city belong to the default city
    return default_city()


class Street(Base):
    """One stretch of street between two junctions (an edge of the routing graph)."""

    __tablename__ = "streets"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_way_id: Mapped[int] = mapped_column(Integer, index=True)
    city: Mapped[str | None] = mapped_column(String(30), index=True, default=_default_city)  # demo city id (assets/demo-data/cities.json)
    name: Mapped[str | None] = mapped_column(String(200))
    road_type: Mapped[str] = mapped_column(String(50))  # OSM highway tag, e.g. primary, residential, footway
    road_class: Mapped[str] = mapped_column(String(20))  # main / residential / lane / underpass (blueprint §7)
    lit: Mapped[str | None] = mapped_column(String(10))  # OSM "lit" tag if mapped: yes / no; usually missing
    in_demo_area: Mapped[bool] = mapped_column(Boolean, default=True)
    start_node: Mapped[int] = mapped_column(Integer, index=True)  # OSM node id
    end_node: Mapped[int] = mapped_column(Integer, index=True)
    length_m: Mapped[float] = mapped_column(Float)
    geometry: Mapped[list] = mapped_column(JSON)  # [[lat, lon], ...]
    map_score: Mapped[float | None] = mapped_column(Float)

    observations: Mapped[list["Observation"]] = relationship(back_populates="street")
    reports: Mapped[list["Report"]] = relationship(back_populates="street")


class Place(Base):
    """A place a person could walk into to ask for help (blueprint §4). Never a guarantee of safety."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[str | None] = mapped_column(String(40), unique=True)  # e.g. "node/123"
    city: Mapped[str | None] = mapped_column(String(30), index=True, default=_default_city)
    name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    opening_hours: Mapped[str | None] = mapped_column(String(300))  # raw OSM-style text
    hours_source: Mapped[str | None] = mapped_column(String(20))  # osm / shadowmap: who gave the hours
    phone: Mapped[str | None] = mapped_column(String(50))
    # Where this place comes from: ["osm"], ["shadowmap"] or ["osm", "shadowmap"] when both describe the same place.
    # Google Places content is never stored here (Google terms); only ShadowMap and OpenStreetMap data.
    sources: Mapped[list] = mapped_column(JSON, default=list)
    in_demo_area: Mapped[bool] = mapped_column(Boolean, default=True)  # False = nearby help outside the 2x2 km box
    osm_last_edited: Mapped[str | None] = mapped_column(String(30))  # when the OSM entry was last edited (not verified)
    duplicate_osm_ids: Mapped[list | None] = mapped_column(JSON)  # other OSM entries merged into this one
    verified_by: Mapped[str | None] = mapped_column(String(80))  # ShadowMap team check in person
    verified_on: Mapped[str | None] = mapped_column(String(20))  # YYYY-MM-DD
    note: Mapped[str | None] = mapped_column(String(300))  # how it was checked
    match_note: Mapped[str | None] = mapped_column(String(200))  # why OSM and ShadowMap entries were treated as one place
    last_seen_open_at: Mapped[datetime | None] = mapped_column(DateTime)


class Observation(Base):
    """One analysed Sentinel photo or video frame (blueprint §6)."""

    __tablename__ = "observations"
    # Live Sentinel duplicate/jump check on every upload: this device's newest photo.
    __table_args__ = (Index("ix_observations_device_captured", "device_id", "captured_at"),)

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

    # How the position was obtained: "gps" (live phone GPS) or "traced_route" (video: estimated along the route the
    # user traced, assuming steady speed). Never claimed as GPS when it is not.
    position_source: Mapped[str | None] = mapped_column(String(20))
    video_job_id: Mapped[int | None] = mapped_column(ForeignKey("video_jobs.id"), index=True)
    frame_time_s: Mapped[float | None] = mapped_column(Float)  # second in the video the frame was taken from
    device_id: Mapped[str | None] = mapped_column(String(64))  # anonymous live-Sentinel device id
    analysis_error: Mapped[str | None] = mapped_column(String(300))

    # M6 privacy pipeline. photo_path = ORIGINAL (restricted, never served; deleted after analysis or at photo_delete_at).
    redaction_status: Mapped[str | None] = mapped_column(String(20))  # None/pending, done, failed
    redacted_path: Mapped[str | None] = mapped_column(String(300))  # blurred copy in REDACTED_DIR
    faces_blurred: Mapped[int | None] = mapped_column(Integer)
    plates_blurred: Mapped[int | None] = mapped_column(Integer)
    photo_public: Mapped[bool | None] = mapped_column(Boolean, default=False)  # True only when redaction AND AI privacy check passed
    privacy_note: Mapped[str | None] = mapped_column(String(200))
    uncertainty: Mapped[str | None] = mapped_column(String(240))
    analysis_attempts: Mapped[int | None] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)

    photo_path: Mapped[str | None] = mapped_column(String(300))  # cleared when the photo is deleted
    photo_delete_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    street: Mapped[Street | None] = relationship(back_populates="observations")


class Report(Base):
    """A one-tap community report (blueprint §10). No free text, by design."""

    __tablename__ = "reports"
    # Rate limit and duplicate check run on every new report: device + time. Place status reads reports by place.
    __table_args__ = (Index("ix_reports_device_created", "device_id", "created_at"), Index("ix_reports_place_id", "place_id"))

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
    # Optimistic locking: every UPDATE checks and raises this number, so a write from an older copy of the walk is
    # refused instead of overwriting newer state (background clock vs. walker's requests). See services/walks.save.
    version: Mapped[int | None] = mapped_column(Integer)
    walker_name: Mapped[str] = mapped_column(String(80))
    walker_phone: Mapped[str | None] = mapped_column(String(30))
    route: Mapped[list] = mapped_column(JSON)  # [[lat, lon], ...]
    city: Mapped[str | None] = mapped_column(String(30), index=True, default=_default_city)  # city the walk was planned in
    dest_lat: Mapped[float] = mapped_column(Float)
    dest_lon: Mapped[float] = mapped_column(Float)
    pin_hash: Mapped[str] = mapped_column(String(200))
    duress_pin_hash: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active / checking / alert / arrived / ended / expired
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expected_arrival_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    last_position_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_moved_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Added for Walk With Me (all nullable so existing databases upgrade safely)
    walker_token_hash: Mapped[str | None] = mapped_column(String(64))  # only the walker's phone can confirm, end, send positions
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lon: Mapped[float | None] = mapped_column(Float)
    route_length_m: Mapped[float | None] = mapped_column(Float)
    last_moved_lat: Mapped[float | None] = mapped_column(Float)
    last_moved_lon: Mapped[float | None] = mapped_column(Float)
    off_route_since: Mapped[datetime | None] = mapped_column(DateTime)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    check_started_at: Mapped[datetime | None] = mapped_column(DateTime)  # "Are you safe?" asked at
    check_trigger: Mapped[str | None] = mapped_column(String(20))
    escalation: Mapped[int | None] = mapped_column(Integer, default=0)  # 0 none, 1 asked, 2 contacts, 3 police
    contacts_alerted_at: Mapped[datetime | None] = mapped_column(DateTime)
    duress: Mapped[bool | None] = mapped_column(Boolean, default=False)  # never revealed to the walker's screen
    simulated: Mapped[bool | None] = mapped_column(Boolean, default=False)  # demo: positions simulated along the route
    events: Mapped[list | None] = mapped_column(JSON)  # timeline for contacts: [{at, kind, text}]
    last_accuracy_m: Mapped[float | None] = mapped_column(Float)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)  # contact link switched off immediately
    pin_failures: Mapped[int | None] = mapped_column(Integer, default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="walk", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="walk", cascade="all, delete-orphan")

    __mapper_args__ = {"version_id_col": version}


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
    lat: Mapped[float | None] = mapped_column(Float)  # walker position when the alert was raised
    lon: Mapped[float | None] = mapped_column(Float)
    history: Mapped[list | None] = mapped_column(JSON)  # [{at, status, by}]
    resolved_reason: Mapped[str | None] = mapped_column(String(100))

    walk: Mapped[Walk] = relationship(back_populates="alerts")


class VideoJob(Base):
    """A night-ride video turned into street observations (blueprint §5 video mode). Processed in the background."""

    __tablename__ = "video_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(300))
    source_kind: Mapped[str] = mapped_column(String(10))  # "upload" or "asset" (file already in assets/videos)
    file_path: Mapped[str] = mapped_column(String(500))  # uploads: our copy in data/videos; assets: read in place
    sentinel_label: Mapped[str] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(30), default=_default_city)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued / processing / done / failed
    stage: Mapped[str | None] = mapped_column(String(40))
    frames_total: Mapped[int | None] = mapped_column(Integer)
    frames_done: Mapped[int | None] = mapped_column(Integer, default=0)
    frames_on_streets: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_s: Mapped[float | None] = mapped_column(Float)
    frame_interval_s: Mapped[float | None] = mapped_column(Float)
    ride_start_s: Mapped[float | None] = mapped_column(Float)  # part of the video that is the ride
    ride_end_s: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime)  # UTC time at video second 0
    recorded_at_source: Mapped[str | None] = mapped_column(String(20))  # "user" or "video_metadata"
    route_waypoints: Mapped[list | None] = mapped_column(JSON)  # [[lat, lon], ...] clicked by the user
    route_geometry: Mapped[list | None] = mapped_column(JSON)  # path along mapped streets through the waypoints
    route_length_m: Mapped[float | None] = mapped_column(Float)
    video_info: Mapped[dict | None] = mapped_column(JSON)  # codec, size, rotation, GPS tag found or not
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Uploaded copies hold unblurred faces and plates: deleted with the photos, 6 h after processing (by the M6 cleanup).
    # Never set for videos in assets/videos, which belong to the team and are never deleted by ShadowMap.
    file_delete_at: Mapped[datetime | None] = mapped_column(DateTime)


class RouteUse(Base):
    """How often a street was on a planned safest route or a started walk — ranks the city repair list (blueprint §11)."""

    __tablename__ = "route_uses"

    street_id: Mapped[int] = mapped_column(ForeignKey("streets.id"), primary_key=True)
    planned: Mapped[int] = mapped_column(Integer, default=0)
    walked: Mapped[int] = mapped_column(Integer, default=0)
