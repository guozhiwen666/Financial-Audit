"""单据、明细与附件表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
金额一律 ``Decimal``，日期一律 ``date``，时间戳一律 ``datetime``。
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schema.enums import (
    AttachmentParseStatus,
    AttachmentStorageStatus,
    DocumentStatus,
    DocumentType,
)

__all__ = [
    "FinancialDocument",
    "DocumentVersion",
    "DocumentLineItem",
    "DocumentAttachment",
    "AttachmentParseResult",
    "InvoiceRecord",
]


@dataclass
class FinancialDocument:
    """financial_documents 表：五类单据的结构化字段。"""

    id: int
    document_type: DocumentType | None = None
    document_no: str | None = None
    applicant_id: int | None = None
    applicant_department: str | None = None
    budget_department: str | None = None
    payee_name: str | None = None
    payee_account: str | None = None
    expense_category: str | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    apply_date: date | None = None
    reason_text: str | None = None
    document_status: DocumentStatus | None = None
    current_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class DocumentVersion:
    """document_versions 表：单据提交快照与版本。"""

    id: int
    document_id: int | None = None
    version_no: int | None = None
    document_snapshot_json: dict[str, Any] | None = None
    created_by: int | None = None
    created_at: datetime | None = None


@dataclass
class DocumentLineItem:
    """document_line_items 表：费用明细与付款明细行。"""

    id: int
    document_id: int | None = None
    item_type: str | None = None
    item_name: str | None = None
    expense_date: date | None = None
    expense_location: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    remark: str | None = None


@dataclass
class DocumentAttachment:
    """document_attachments 表：非结构化附件元信息。"""

    id: int
    document_id: int | None = None
    document_version: int | None = None
    file_name: str | None = None
    file_type: str | None = None
    file_size: int | None = None
    file_path: str | None = None
    file_hash: str | None = None
    storage_status: AttachmentStorageStatus | None = None
    parse_status: AttachmentParseStatus | None = None
    created_at: datetime | None = None


@dataclass
class AttachmentParseResult:
    """attachment_parse_results 表：附件解析产物。

    保存 PRD 2.7.2 要求的解析文本、字段提取结果、页码、文本位置与识别置信度。
    """

    id: int
    attachment_id: int | None = None
    document_category: str | None = None
    full_text: str | None = None
    fields_json: dict[str, Any] | None = None
    evidence_positions_json: dict[str, Any] | None = None
    confidence: float | None = None
    created_at: datetime | None = None


@dataclass
class InvoiceRecord:
    """invoice_records 表：发票结构化记录。"""

    id: int
    attachment_id: int | None = None
    invoice_code: str | None = None
    invoice_no: str | None = None
    seller_name: str | None = None
    buyer_name: str | None = None
    invoice_date: date | None = None
    amount_excluding_tax: Decimal | None = None
    tax_amount: Decimal | None = None
    amount_including_tax: Decimal | None = None
    currency: str | None = None
