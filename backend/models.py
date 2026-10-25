"""Database models. Works with SQLite (default) and PostgreSQL (DATABASE_URL)."""
from datetime import datetime, timezone

from flask import g, current_app
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, event, Index)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Shop(Base):
    __tablename__ = "shops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    district: Mapped[str] = mapped_column(String(80), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str] = mapped_column(String(32), default="")
    hours: Mapped[str] = mapped_column(String(64), default="")
    instagram: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # pending -> active (approved by an admin) ; blocked
    status: Mapped[str] = mapped_column(String(16), default="pending")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    founding_partner: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    link_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    products: Mapped[list["Product"]] = relationship(back_populates="shop", cascade="all, delete-orphan")

    def public(self, distance_km=None):
        data = {
            "id": self.id, "slug": self.slug, "name": self.name, "district": self.district,
            "address": self.address, "lat": self.lat, "lng": self.lng, "phone": self.phone,
            "hours": self.hours, "instagram": self.instagram, "description": self.description,
            "verified": self.status == "active" and not self.is_demo, "demo": self.is_demo,
            "founding_partner": self.founding_partner,
        }
        if distance_km is not None:
            data["distance_km"] = round(distance_km, 2)
        return data


class Seller(Base):
    __tablename__ = "sellers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    login: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    shop: Mapped[Shop] = relationship()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60), index=True)
    color: Mapped[str] = mapped_column(String(40), default="")
    price: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    image: Mapped[str | None] = mapped_column(String(120), nullable=True)
    search_text: Mapped[str] = mapped_column(Text, default="")
    # Stylist attributes: who it is for, when and where it is worn, how warm it is (0-3)
    gender: Mapped[str] = mapped_column(String(10), default="unisex", server_default="unisex")
    seasons: Mapped[str] = mapped_column(String(40), default="", server_default="")
    occasions: Mapped[str] = mapped_column(String(80), default="", server_default="")
    warmth: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # JSON {"author", "license", "license_url", "source_url"} for openly licensed demo photos
    photo_credit: Mapped[str] = mapped_column(Text, default="", server_default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="products")
    variants: Mapped[list["Variant"]] = relationship(back_populates="product", cascade="all, delete-orphan",
                                                     order_by="Variant.position")


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("product_id", "size"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    size: Mapped[str] = mapped_column(String(16))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="variants")


class Buyer(Base):
    __tablename__ = "buyers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True)
    visitor: Mapped[str] = mapped_column(String(64), default="", index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(String(300), default="")
    # pending -> confirmed -> visited | sold ; pending -> declined | expired ; any active -> cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirm_by: Mapped[datetime] = mapped_column(DateTime)
    hold_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    shop: Mapped[Shop] = relationship()
    product: Mapped[Product] = relationship()
    variant: Mapped[Variant] = relationship()
    buyer: Mapped[Buyer | None] = relationship()


ACTIVE_RESERVATION = ("pending", "confirmed")


class Event(Base):
    """Funnel events for shop statistics: view, tryon, reservation, visit, share."""
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_shop_kind_time", "shop_id", "kind", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    visitor: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TryOnJob(Base):
    __tablename__ = "tryon_jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    visitor: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|processing|completed|failed
    error: Mapped[str] = mapped_column(String(255), default="")
    photo_path: Mapped[str] = mapped_column(String(255), default="")
    result_path: Mapped[str] = mapped_column(String(255), default="")
    keep: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Share(Base):
    """'Oilamga yuborib so'ray': a link with 1-4 products that friends can vote on."""
    __tablename__ = "shares"
    token: Mapped[str] = mapped_column(String(24), primary_key=True)
    product_ids: Mapped[str] = mapped_column(String(120))  # comma-separated ids
    question: Mapped[str] = mapped_column(String(160), default="")
    visitor: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ShareVote(Base):
    __tablename__ = "share_votes"
    __table_args__ = (UniqueConstraint("share_token", "voter"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_token: Mapped[str] = mapped_column(ForeignKey("shares.token", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(Integer)
    voter: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Database:
    def __init__(self, url):
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        self.engine = create_engine(url, future=True, pool_pre_ping=True, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _pragmas(conn, _):
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_all(self):
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()

    def _add_missing_columns(self):
        """Additive migration: create columns added to the models after a table already existed."""
        from sqlalchemy import inspect, text
        inspector = inspect(self.engine)
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing:
                        continue
                    ddl = column.type.compile(dialect=self.engine.dialect)
                    default = column.server_default.arg if column.server_default is not None else None
                    clause = f" DEFAULT '{default}'" if isinstance(default, str) else ""
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl}{clause}'))


def db():
    """The request-scoped session (closed in teardown)."""
    if "db" not in g:
        g.db = current_app.extensions["clothes_db"].Session()
    return g.db
