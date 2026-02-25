"""PDF-related Pydantic schemas."""

from datetime import datetime
from typing import Annotated, Any, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PDFResponse(BaseModel):
    id: UUID
    name: str
    size_bytes: int
    page_count: Optional[int] = None
    status: str
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PDFListResponse(BaseModel):
    items: List[PDFResponse]
    total: int
    page: int
    size: int


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def must_end_with_pdf(cls, v: str) -> str:
        if not v.lower().endswith(".pdf"):
            raise ValueError("Filename must end with .pdf")
        return v.strip()


class UploadResponseItem(BaseModel):
    pdf_id: UUID
    filename: str
    status: str
    task_id: str


class UploadResponse(BaseModel):
    files: List[UploadResponseItem]
    total: int


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str  # PENDING | STARTED | SUCCESS | FAILURE | RETRY
    result: Any = None
    progress: Optional[int] = None


class PDFDetailResponse(BaseModel):
    id: str
    name: str
    status: str
    page_count: Optional[int] = None
    size_bytes: int


class TextOp(BaseModel):
    type: Literal["text"]
    page: int = Field(ge=0)
    x: float
    y: float
    text: str = Field(min_length=1, max_length=2000)
    font_family: str = Field(default="Helvetica")
    font_size: float = Field(default=12.0, ge=4.0, le=200.0)
    bold: bool = False
    italic: bool = False
    color_hex: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    rotation: float = Field(default=0.0)


class HighlightOp(BaseModel):
    type: Literal["highlight"]
    page: int = Field(ge=0)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    color_hex: str = Field(default="#FFFF00", pattern=r"^#[0-9A-Fa-f]{6}$")
    opacity: float = Field(default=0.4, ge=0.1, le=1.0)


class EraseOp(BaseModel):
    type: Literal["erase"]
    page: int = Field(ge=0)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    fill_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")


class ShapeOp(BaseModel):
    type: Literal["shape"]
    shape_type: Literal["rectangle", "line"]
    page: int = Field(ge=0)
    x: float
    y: float
    width: float
    height: float
    stroke_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    fill_color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    stroke_width: float = Field(default=1.5, gt=0)


class DrawOp(BaseModel):
    type: Literal["draw"]
    page: int = Field(ge=0)
    path: str = Field(max_length=50000)
    color_hex: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    stroke_width: float = Field(default=2.0, gt=0)


class PageOp(BaseModel):
    type: Literal["page"]
    action: Literal["delete", "rotate", "reorder"]
    page: int = Field(ge=0)
    rotate_degrees: Optional[int] = None
    new_order: Optional[List[int]] = None


EditOp = Annotated[
    Union[TextOp, HighlightOp, EraseOp, ShapeOp, DrawOp, PageOp],
    Field(discriminator="type"),
]


class EditRequest(BaseModel):
    operations: List[EditOp] = Field(max_length=500)
    comment: Optional[str] = Field(default=None, max_length=500)


class EditResponseItem(BaseModel):
    pdf_id: UUID
    version: int
    saved_at: datetime
    task_id: str


class VersionResponse(BaseModel):
    id: UUID
    version: int
    saved_at: datetime
    saved_by: UUID

    model_config = ConfigDict(from_attributes=True)
