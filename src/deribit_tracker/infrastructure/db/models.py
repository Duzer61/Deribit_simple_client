"""ORM-модель наблюдений index price."""

from decimal import Decimal
from typing import Final

from sqlalchemy import BigInteger, CheckConstraint, Index, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from deribit_tracker.domain.models import SUPPORTED_TICKERS

TABLE_NAME: Final = "price_observations"
INDEX_NAME: Final = "ix_price_observations_ticker_timestamp_id"

_SUPPORTED_TICKER_VALUES: Final = ", ".join(f"'{ticker.value}'" for ticker in SUPPORTED_TICKERS)
_TICKER_CHECK: Final = f"ticker IN ({_SUPPORTED_TICKER_VALUES})"


class Base(DeclarativeBase):
    """Декларативная база ORM-моделей."""


class PriceObservationRow(Base):
    """Строка таблицы ``price_observations``.

    ``price`` хранится как ``NUMERIC(30, 12)`` (точное десятичное значение),
    ``timestamp`` — как ``BIGINT`` (секунды UNIX UTC). Набор тикеров, положительность
    цены и неотрицательность времени закреплены CHECK-ограничениями.
    """

    __tablename__ = TABLE_NAME

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        CheckConstraint(_TICKER_CHECK, name="ck_price_observations_ticker"),
        CheckConstraint("price > 0", name="ck_price_observations_price_positive"),
        CheckConstraint("timestamp >= 0", name="ck_price_observations_timestamp_non_negative"),
        Index(INDEX_NAME, "ticker", "timestamp", "id"),
    )
