"""附件接口（PRD 13.4 附件）。

覆盖：上传、下载或预览、删除、创建解析任务。
下载与预览按 PRD 16 做「单据数据权限 + 附件归属单据」双重校验，禁止通过裸路径直接访问。
"""

from typing import Annotated
from urllib.parse import quote  # 文件名的 URL 编码（含中文）

from fastapi import APIRouter, Header, UploadFile
from fastapi.responses import Response  # 附件内容响应

from service.infrastructure import idempotency, runtime
from service.business_services import attachment_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict
from service.infrastructure.errors import BadRequest

__all__ = ["router"]

router = APIRouter(tags=["附件"])

# 预览用的内容类型：PRD 2.7.2 支持三种格式
_MEDIA_TYPES = {"PDF": "application/pdf", "PNG": "image/png", "JPG": "image/jpeg",
                "JPEG": "image/jpeg"}


@router.post("/documents/{document_id}/attachments")
async def upload_attachment(document_id: int, file: UploadFile,
                            principal: CurrentPrincipal) -> dict:
    """上传单据附件（PRD 13.4 POST /documents/{document_id}/attachments）。"""
    # 步骤 1：读取文件内容；空文件在服务层校验中被拒绝（PRD 16 校验文件大小）
    content = await file.read()
    if not content:
        raise BadRequest("上传内容为空")
    # 步骤 2：交服务层做格式校验、落盘与记录落库
    attachment = attachment_service.upload(document_id, file.filename or "未命名",
                                           content, principal.role_codes, principal.user_id)
    return {"attachment": as_dict(attachment)}


@router.get("/documents/{document_id}/attachments/{attachment_id}")
def download_attachment(document_id: int, attachment_id: int, principal: CurrentPrincipal,
                        preview: bool = False) -> Response:
    """下载或预览单据附件（PRD 13.4 GET /documents/{document_id}/attachments/{attachment_id}）。"""
    # 步骤 1：双重权限校验后读取内容（PRD 16）
    content, attachment = attachment_service.download(document_id, attachment_id,
                                                      principal.role_codes, principal.user_id)
    # 步骤 2：按 file_type 指定内容类型；preview 时浏览器内联展示，否则触发下载
    media_type = _MEDIA_TYPES.get((attachment.file_type or "").upper(), "application/octet-stream")
    disposition = "inline" if preview else "attachment"
    file_name = quote(attachment.file_name or "attachment")
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": "%s; filename*=UTF-8''%s"
                                                    % (disposition, file_name)})


@router.delete("/documents/{document_id}/attachments/{attachment_id}")
def delete_attachment(document_id: int, attachment_id: int, principal: CurrentPrincipal) -> dict:
    """删除单据附件（PRD 13.4 DELETE /documents/{document_id}/attachments/{attachment_id}）。"""
    affected = attachment_service.delete(document_id, attachment_id, principal.role_codes,
                                         principal.user_id)
    return {"deleted": affected}


@router.post("/documents/{document_id}/attachments/{attachment_id}/parse")
def parse_attachment(document_id: int, attachment_id: int, principal: CurrentPrincipal,
                     idempotency_key: Annotated[str, Header()] = "") -> dict:
    """创建附件解析任务（PRD 13.4 POST parse、11.1 幂等性）。"""
    # 步骤 1：按幂等键执行，重复请求复用首次解析结果，不重复调用 OCR 与大模型
    result = idempotency.run_once(
        idempotency_key, "parse:%s" % attachment_id,
        lambda: attachment_service.parse(document_id, attachment_id, principal.role_codes,
                                         principal.user_id))
    # 步骤 2：解析失败时结果为空，但仍返回当前解析状态与实时消息，供前端展示并允许重试（PRD 8.1 第 9 条）
    return {"parse_result": as_dict(result),
            "messages": as_list(runtime.messages_since(0))}
