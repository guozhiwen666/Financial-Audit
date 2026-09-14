"""单据、明细与附件表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
金额一律 ``Decimal``，日期一律 ``date``，时间戳一律 ``datetime``。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import date, datetime      # date：业务日期；datetime：时间戳
from decimal import Decimal              # Decimal：金额/数量，禁止 float 以免精度丢失
from typing import Any                   # Any：JSON 列内的值类型不固定

from schema.enums import (
    AttachmentParseStatus,               # 附件解析状态
    AttachmentStorageStatus,             # 附件存储状态
    DocumentStatus,                      # 单据状态
    DocumentType,                        # 单据类型
)

__all__ = [
    "FinancialDocument",       # 单据主表
    "DocumentVersion",         # 单据版本快照表
    "DocumentLineItem",        # 单据明细表
    "DocumentAttachment",      # 附件表
    "AttachmentParseResult",   # 附件解析结果表
    "InvoiceRecord",           # 发票记录表
]


@dataclass
class FinancialDocument:
    """financial_documents 表：五类单据的结构化字段。"""

    id: int                                              # 主键
    document_type: DocumentType | None = None            # 单据类型，五类之一
    document_no: str | None = None                       # 单据编号，系统内唯一
    applicant_id: int | None = None                      # 申请人的用户主键，指向 users.id
    applicant_department: str | None = None              # 申请部门
    budget_department: str | None = None                 # 预算部门，可与申请部门不同
    payee_name: str | None = None                        # 收款单位（报销类为报销人）
    payee_account: str | None = None                     # 收款账号，参与重复收款识别
    expense_category: str | None = None                  # 费用类别，用于匹配费用标准
    total_amount: Decimal | None = None                  # 单据总金额
    currency: str | None = None                          # 币种（PRD 未列举取值，保持字符串）
    apply_date: date | None = None                       # 申请日期
    reason_text: str | None = None                       # 事由，说明本次付款/报销原因
    document_status: DocumentStatus | None = None        # 单据当前状态
    current_version: int | None = None                   # 当前版本号，重新提交时递增
    created_at: datetime | None = None                   # 创建时间
    updated_at: datetime | None = None                   # 最近一次更新时间


@dataclass
class DocumentVersion:
    """document_versions 表：单据提交快照与版本，用于追溯历史形态。"""

    id: int                                                  # 主键
    document_id: int | None = None                           # 所属单据主键，指向 financial_documents.id
    version_no: int | None = None                            # 版本号，从 1 递增
    document_snapshot_json: dict[str, Any] | None = None     # 该版本的单据字段与明细完整快照
    created_by: int | None = None                            # 快照生成人（提交人），指向 users.id
    created_at: datetime | None = None                       # 快照生成时间


@dataclass
class DocumentLineItem:
    """document_line_items 表：费用明细与付款明细行。"""

    id: int                                        # 主键
    document_id: int | None = None                 # 所属单据主键，指向 financial_documents.id
    item_type: str | None = None                   # 明细类型（费用明细/付款明细，取值 PRD 未列举）
    item_name: str | None = None                   # 明细名称（商品、服务或费用名称）
    expense_date: date | None = None               # 消费日期/付款日期
    expense_location: str | None = None            # 消费地点
    quantity: Decimal | None = None                # 数量，可为小数（如时长、重量）
    unit_price: Decimal | None = None              # 单价
    amount: Decimal | None = None                  # 本行金额（单笔金额/报销金额）
    remark: str | None = None                      # 备注说明


@dataclass
class DocumentAttachment:
    """document_attachments 表：非结构化附件元信息（支持 PDF、PNG、JPG）。"""

    id: int                                                    # 主键
    document_id: int | None = None                             # 所属单据主键，指向 financial_documents.id
    document_version: int | None = None                        # 附件对应的单据版本号
    file_name: str | None = None                               # 原始文件名
    file_type: str | None = None                               # 文件类型（如 PDF/PNG/JPG）
    file_size: int | None = None                               # 文件大小（字节）
    file_path: str | None = None                               # 存储路径，禁止对外暴露
    file_hash: str | None = None                               # 文件哈希，用于防篡改与去重核对
    storage_status: AttachmentStorageStatus | None = None       # 存储状态（上传中/已存储/失败）
    parse_status: AttachmentParseStatus | None = None           # 解析状态（待解析/成功/失败等）
    created_at: datetime | None = None                          # 上传时间


@dataclass
class AttachmentParseResult:
    """attachment_parse_results 表：附件解析产物。

    保存 PRD 2.7.2 要求的解析文本、字段提取结果、页码、文本位置与识别置信度。
    """

    id: int                                                    # 主键
    attachment_id: int | None = None                           # 所属附件主键，指向 document_attachments.id
    document_category: str | None = None                       # 文档分类（发票/合同/行程单等，取值 PRD 未列举）
    full_text: str | None = None                               # 附件解析出的全文文本
    fields_json: dict[str, Any] | None = None                  # 字段提取结果（字段名、值、页码、置信度）
    evidence_positions_json: dict[str, Any] | None = None      # 文本位置信息（页码与归一化坐标）
    confidence: float | None = None                            # 整体识别置信度 0~1
    created_at: datetime | None = None                         # 解析完成时间


@dataclass
class InvoiceRecord:
    """invoice_records 表：发票结构化记录。"""

    id: int                                          # 主键
    attachment_id: int | None = None                 # 来源附件主键，指向 document_attachments.id
    invoice_code: str | None = None                  # 发票代码
    invoice_no: str | None = None                    # 发票号码
    seller_name: str | None = None                   # 销售方名称
    buyer_name: str | None = None                    # 购买方名称
    invoice_date: date | None = None                 # 开票日期
    amount_excluding_tax: Decimal | None = None      # 不含税金额
    tax_amount: Decimal | None = None                # 税额
    amount_including_tax: Decimal | None = None      # 含税金额，参与单据与发票金额一致性校验
    currency: str | None = None                      # 币种（PRD 未列举取值，保持字符串）
