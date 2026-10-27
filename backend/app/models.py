"""ORM models: uploaded statements, their transactions, and learned merchant categories."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_kept: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_removed: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[float] = mapped_column(Float)  # negative = money out, positive = money in
    category: Mapped[str] = mapped_column(String(60), index=True)
    category_source: Mapped[str] = mapped_column(String(20), default="rule")  # rule | learned | llm | user | default

    statement: Mapped[Statement] = relationship(back_populates="transactions")


class MerchantCategory(Base):
    """Categories learned from user corrections or the LLM, reused on future uploads."""

    __tablename__ = "merchant_categories"

    merchant: Mapped[str] = mapped_column(String(120), primary_key=True)
    category: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(20))  # user | llm
