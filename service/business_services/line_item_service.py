"""明细模块（PRD 11 章「明细模块」、13.3）。

职责：费用明细与付款明细的维护、金额计算与明细校验。
边界：合计校验（PRD 5.3 分类型合计口径）在环节一随提交执行，本模块只负责明细的增删改查与
单行金额计算，不重复实现合计规则。
"""

from decimal import Decimal  # 金额精确计算（PRD 12.2 金额用定点数，禁止浮点）

from schema.tables_document import DocumentLineItem  # 明细行实体
from service.infrastructure import repository as repo
from service.business_services import auth_service, document_service
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["LINE_ITEM_FIELDS", "list_line_items", "add_line_item", "update_line_item",
           "delete_line_item"]

# 可由接口直接写入的列：取数据表真实列并排除主键与所属单据
LINE_ITEM_FIELDS = tuple(c for c in repo.document_line_items.columns
                         if c not in ("id", "document_id"))

# 可维护明细的单据状态：草稿与已退回（PRD 7.3 仅这两类状态可编辑）
EDITABLE_STATUSES = {"draft", "returned"}


def _require_editable(document_id: int, role_codes: list[str], user_id: int):
    """取单据并校验「可编辑明细」的前置条件，返回单据实体。"""
    # 步骤 1：单据必须存在
    document = document_service.require_document(document_id)
    # 步骤 2：数据权限——申请人仅限本人单据（PRD 3.2、3.3）
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可维护该单据的明细")
    # 步骤 3：状态闸口——仅草稿与已退回可维护明细（PRD 7.3 流转表）
    if (document.document_status or "").value not in EDITABLE_STATUSES:
        raise BadRequest("当前状态 %s 不可维护明细（PRD 7.3）" % document.document_status.value)
    return document


def list_line_items(document_id: int, role_codes: list[str],
                    user_id: int) -> list[DocumentLineItem]:
    """查询单据的全部明细（PRD 13.2 单据详情包含明细）。"""
    # 步骤 1：复用单据详情做权限校验——无权查看单据即无权查看其明细（PRD 3.3）
    detail = document_service.detail(document_id, role_codes, user_id)
    return detail["line_items"]


def add_line_item(document_id: int, payload: dict, role_codes: list[str],
                  user_id: int) -> DocumentLineItem:
    """新增单据明细（PRD 13.3 POST /documents/{id}/line-items）。"""
    _require_editable(document_id, role_codes, user_id)
    # 步骤 1：字段白名单校验，避免静默丢弃请求字段
    unknown = set(payload) - set(LINE_ITEM_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 2：按字段类型转换后构造实体（主键待落库回填故以 0 占位）
    item = DocumentLineItem(id=0, document_id=document_id)
    for name, value in payload.items():
        setattr(item, name, repo.document_line_items.coerce(name, value))
    # 步骤 3：单行金额计算——数量与单价齐备而金额未给时按乘积取（PRD 11 章明细模块「金额计算」）
    if item.amount is None and item.quantity is not None and item.unit_price is not None:
        item.amount = (item.quantity * item.unit_price).quantize(Decimal("0.01"))
    # 步骤 4：落库并回填主键
    item.id = repo.document_line_items.insert(item)
    return item


def update_line_item(document_id: int, line_item_id: int, payload: dict, role_codes: list[str],
                     user_id: int) -> DocumentLineItem:
    """更新单据明细（PRD 13.3 PATCH /documents/{id}/line-items/{line_item_id}）。"""
    _require_editable(document_id, role_codes, user_id)
    # 步骤 1：明细必须存在且确实属于该单据，防止跨单据越权修改
    item = repo.document_line_items.get(line_item_id)
    if item is None or item.document_id != document_id:
        raise NotFound("明细不存在：%s" % line_item_id)
    # 步骤 2：字段白名单校验
    unknown = set(payload) - set(LINE_ITEM_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 3：写入变更列
    values = {name: repo.document_line_items.coerce(name, value) for name, value in payload.items()}
    repo.document_line_items.update(line_item_id, **values)
    # 步骤 4：返回更新后的实体
    return repo.document_line_items.get(line_item_id)


def delete_line_item(document_id: int, line_item_id: int, role_codes: list[str],
                     user_id: int) -> int:
    """删除单据明细（PRD 13.3 DELETE /documents/{id}/line-items/{line_item_id}）。"""
    _require_editable(document_id, role_codes, user_id)
    # 步骤 1：校验明细归属，防止跨单据越权删除
    item = repo.document_line_items.get(line_item_id)
    if item is None or item.document_id != document_id:
        raise NotFound("明细不存在：%s" % line_item_id)
    # 步骤 2：删除并返回受影响行数
    return repo.document_line_items.delete(line_item_id)
