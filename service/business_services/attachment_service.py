"""附件模块（PRD 11 章「附件模块」、13.4、2.7.9、16）。

职责：附件上传、保存、删除、下载、格式校验、访问控制与解析任务创建。
边界：文件落盘由 ``service.storage`` 负责，解析由环节二转交 A2 负责；
本模块只做权限拦截、记录落库与解析结果归档。
访问控制（PRD 16）：附件为高危资源，下载与预览需「单据数据权限 + 附件归属单据」双重校验。
"""

import datetime  # 发票开票日期的解析
from decimal import Decimal, InvalidOperation  # 发票金额的精确解析
from pathlib import Path  # 存储相对路径与绝对路径的判断

from schema.tables_document import DocumentAttachment, InvoiceRecord  # 附件与发票实体
from service.infrastructure import repository as repo, runtime, storage
from service.business_services import auth_service, document_service
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["upload", "download", "delete", "parse", "require_attachment", "for_parsing"]


def for_parsing(attachments: list) -> list:
    """把附件的存储相对路径解析为绝对路径，供解析环节读取文件（PRD 2.7.9 附件模块）。

    数据库保存的是受控的存储相对路径（禁止对外暴露绝对路径，PRD 16）；
    解析时须先解析为绝对路径才能打开文件，故在此统一转换。
    """
    for attachment in attachments:
        if attachment.file_path and not Path(attachment.file_path).is_absolute():
            attachment.file_path = str(storage.absolute_path(attachment.file_path))
    return attachments

# 解析结果中标识发票类的分类关键词：A2 的文档分类由大模型给出，此处只按关键词判定归属
INVOICE_KEYWORD = "发票"
# 发票字段的抽取键名：与 invoice_records 的列名保持一致，便于直接归档
INVOICE_FIELDS = ("invoice_code", "invoice_no", "seller_name", "buyer_name", "invoice_date",
                  "amount_excluding_tax", "tax_amount", "amount_including_tax", "currency")


def _require_document_permission(document_id: int, role_codes: list[str], user_id: int) -> None:
    """校验对所属单据的数据权限；无权时抛 PermissionDenied（PRD 3.3、16）。"""
    document = document_service.require_document(document_id)
    if not auth_service.can_view_document(role_codes, user_id, document):
        raise PermissionDenied("无权访问该单据的附件")


def require_attachment(document_id: int, attachment_id: int, role_codes: list[str],
                       user_id: int) -> DocumentAttachment:
    """取附件并做双重校验：单据数据权限 + 附件归属该单据（PRD 16）。"""
    # 步骤 1：先校验所属单据的数据权限
    _require_document_permission(document_id, role_codes, user_id)
    # 步骤 2：再校验附件确实属于该单据，禁止通过裸 ID 跨单据访问
    attachment = repo.document_attachments.get(attachment_id)
    if attachment is None or attachment.document_id != document_id:
        raise NotFound("附件不存在：%s" % attachment_id)
    return attachment


def upload(document_id: int, file_name: str, content: bytes, role_codes: list[str],
           user_id: int) -> DocumentAttachment:
    """上传单据附件（PRD 13.4 POST /documents/{id}/attachments）。"""
    # 步骤 1：权限校验——仅申请人本人可维护本人单据的附件（PRD 3.2）
    document = document_service.require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可上传该单据的附件")
    # 步骤 2：格式与大小校验（PRD 16 校验文件类型与大小）
    errors = storage.validate_upload(file_name, len(content))
    if errors:
        raise BadRequest("；".join(errors))
    # 步骤 3：落盘，取得相对路径、字节数与内容哈希
    file_path, file_size, file_hash = storage.save(document_id, file_name, content)
    # 步骤 4：交环节二构造附件实体（内部按 PRD 5.4 做格式闸口并置存储/解析状态）
    attachment = runtime.flow().attachment.upload(document_id, file_name, file_path,
                                                  file_size, file_hash)
    if attachment is None:
        raise BadRequest("不支持的文件格式，仅支持 PDF、PNG、JPG（PRD 5.4）")
    # 步骤 5：落库并回填主键
    attachment.id = repo.document_attachments.insert(attachment)
    return attachment


def download(document_id: int, attachment_id: int, role_codes: list[str],
             user_id: int) -> tuple[bytes, DocumentAttachment]:
    """下载或预览附件，返回 (文件内容, 附件实体)（PRD 13.4 GET）。"""
    # 步骤 1：双重校验后取附件实体（PRD 16 禁止裸路径访问）
    attachment = require_attachment(document_id, attachment_id, role_codes, user_id)
    # 步骤 2：按存储相对路径读取内容；路径穿越由 storage 拦截
    if not attachment.file_path:
        raise NotFound("附件尚未存储完成：%s" % attachment_id)
    return storage.read(attachment.file_path), attachment


def delete(document_id: int, attachment_id: int, role_codes: list[str], user_id: int) -> int:
    """删除单据附件（PRD 13.4 DELETE）。"""
    # 步骤 1：双重校验；仅申请人本人可删本人单据的附件
    document = document_service.require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可删除该单据的附件")
    attachment = require_attachment(document_id, attachment_id, role_codes, user_id)
    # 步骤 2：先删解析结果与发票记录，再删附件记录，最后删文件——避免留下孤儿数据
    for result in repo.attachment_parse_results.find("attachment_id = %s", (attachment_id,)):
        repo.attachment_parse_results.delete(result.id)
    for invoice in repo.invoice_records.find("attachment_id = %s", (attachment_id,)):
        repo.invoice_records.delete(invoice.id)
    affected = repo.document_attachments.delete(attachment_id)
    # 步骤 3：删除落盘文件；文件缺失不影响记录删除的结果
    if attachment.file_path:
        storage.delete(attachment.file_path)
    # 步骤 4：写审计留痕（PRD 2.7.9 日志模块「附件访问」）
    runtime.flow().audit_log.record("delete_attachment", "document_attachments", attachment_id,
                                    user_id, {"file_name": attachment.file_name})
    runtime.flush_audit_logs()
    return affected


def parse(document_id: int, attachment_id: int, role_codes: list[str], user_id: int):
    """创建并执行附件解析任务：OCR、字段提取、证据定位（PRD 13.4 POST parse、2.7.5）。"""
    # 步骤 1：双重校验后取附件
    attachment = require_attachment(document_id, attachment_id, role_codes, user_id)
    # 步骤 2：把存储相对路径解析为绝对路径后交环节二（解析需要真实文件路径）
    original_path = attachment.file_path
    for_parsing([attachment])
    try:
        # 步骤 3：交环节二解析——内部转交 A2，并按 PRD 5.4 回写解析状态（失败可重试）
        result = runtime.flow().attachment.parse(attachment)
    finally:
        # 步骤 4：还原相对路径，避免把绝对路径写回数据库（PRD 16 附件路径受控）
        attachment.file_path = original_path
    # 步骤 5：回写解析状态到数据库
    repo.document_attachments.update(attachment.id, parse_status=attachment.parse_status)
    # 步骤 6：归档解析结果（失败时无结果可归档，状态已标 failed）
    if result is not None:
        result.id = repo.attachment_parse_results.insert(result)
        _archive_invoice(result)
    return result


def _archive_invoice(result) -> int | None:
    """发票类附件的解析结果同步归档为发票记录（PRD 12.1 invoice_records、2.7.5）。"""
    # 步骤 1：仅处理分类为发票且确实抽到发票号的解析结果，避免产生空记录
    fields = result.fields_json or {}
    if INVOICE_KEYWORD not in (result.document_category or ""):
        return None
    if not (fields.get("invoice_no") or fields.get("invoice_code")):
        return None
    # 步骤 2：按 invoice_records 的列逐一取值归档；缺字段保持空，不臆造
    record = InvoiceRecord(id=0, attachment_id=result.attachment_id,
                           currency=fields.get("currency"))
    for name in INVOICE_FIELDS:
        value = fields.get(name)
        if name == "invoice_date":
            record.invoice_date = _as_date(value)
        elif name in ("amount_excluding_tax", "tax_amount", "amount_including_tax"):
            setattr(record, name, _as_decimal(value))
        elif value is not None:
            setattr(record, name, str(value))
    # 步骤 3：落库并回填主键
    record.id = repo.invoice_records.insert(record)
    return record.id


def _as_decimal(value) -> Decimal | None:
    """把解析出的金额文本转为 Decimal；无法解析时返回 None（不静默置零）。"""
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("¥", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _as_date(value) -> datetime.date | None:
    """把解析出的日期文本转为 date；支持常见的年月日写法，无法解析时返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip().replace("年", "-").replace("月", "-").replace("日", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
