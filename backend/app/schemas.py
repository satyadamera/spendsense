from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from .categorizer import CATEGORIES


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_at: datetime | None
    period_start: date | None
    period_end: date | None
    rows_read: int
    rows_kept: int
    duplicates_removed: int
    invalid_rows: int


class UploadResult(BaseModel):
    statement: StatementOut
    warnings: list[str]
    categorised_by: dict[str, int]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    statement_id: int
    date: date
    description: str
    merchant: str
    amount: float
    category: str
    category_source: str


class CategoryUpdate(BaseModel):
    category: str
    apply_to_merchant: bool = True

    @field_validator("category")
    @classmethod
    def known_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
        return v
