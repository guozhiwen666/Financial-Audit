"""环节二 附件管理（PRD 2.7.1 附件能力、解析能力）。

职责：附件上传与格式校验（PDF / PNG / JPG）、创建解析任务并执行解析、按置信度阈值标注解析状态。
解析本身交由 **A2 凭证解析智能体**（PRD 20.2），本环节只负责格式闸口与解析状态回写。

边界：不做金额合规判断、不给风险等级、不修改单据结构化字段、不判定发票真伪（PRD 2.7.1、20.2）。
格式白名单与置信度阈值直接取自 A2 对外公开的常量，避免两处漂移。数据持久化未实现，故只产出实体。
"""

from datetime import datetime, timezone  # 附件上传时间戳（PRD 12.2：时间戳统一 UTC）

from agent.document_parser_agent.main_flow import (  # A2 凭证解析智能体及其公开常量
    CONFIDENCE_THRESHOLD,  # 低置信度阈值：低于该值转人工复核（PRD 5.4）
    SUPPORTED_FORMATS,     # 允许的附件格式：PDF / PNG / JPG（PRD 5.4）
    DocumentParserAgent,
)
from schema.enums import AttachmentParseStatus, AttachmentStorageStatus  # 存储状态与解析状态
from schema.tables_document import AttachmentParseResult, DocumentAttachment  # 附件与解析结果

__all__ = ["AttachmentFlow"]


class AttachmentFlow:
    """环节二 附件管理（PRD 2.7.1 附件能力、解析能力）。"""

    def __init__(self, parser: DocumentParserAgent) -> None:
        """注入下游解析智能体；文件存储与访问控制由后端附件模块负责，不在本环节。"""
        self.parser = parser  # 解析交由 A2 凭证解析智能体（PRD 20.2）

    def upload(self, document_id: int, file_name: str, file_path: str, file_size: int,
               file_hash: str) -> DocumentAttachment | None:
        """上传附件并校验格式（PDF / PNG / JPG），返回附件实体；格式不合规则返回 None。

        存储路径、大小与哈希由调用方（附件接口）在接收文件时取得后传入（PRD 2.7.9 附件模块）。
        """
        # 步骤 1：从文件名取出扩展名并统一大写，作为格式判据；无扩展名则视为空类型
        file_type = file_name.rsplit(".", 1)[-1].upper() if "." in file_name else ""
        # 步骤 2：格式闸口——PRD 5.4 仅支持 PDF / PNG / JPG，不合规直接拒绝，不产出任何实体
        if file_type not in SUPPORTED_FORMATS:
            return None
        # 步骤 3：构造附件实体；主键待落库后回填故以 0 占位；已存储、待解析（PRD 5.4 存储/解析状态）
        return DocumentAttachment(id=0,
                                  document_id=document_id,     # 所属单据主键
                                  file_name=file_name,         # 原始文件名，用于展示与证据对照
                                  file_type=file_type,         # 格式（PDF / PNG / JPG）
                                  file_size=file_size,         # 文件大小，供上传限制与展示
                                  file_path=file_path,         # 存储路径，禁止对外暴露（PRD 16 安全边界）
                                  file_hash=file_hash,         # 文件哈希，用于防篡改与去重核对
                                  storage_status=AttachmentStorageStatus.STORED,
                                  parse_status=AttachmentParseStatus.PENDING,
                                  created_at=datetime.now(timezone.utc))

    def parse(self, attachment: DocumentAttachment) -> AttachmentParseResult | None:
        """创建附件解析任务并执行解析：OCR、字段提取与原文证据定位（PRD 2.7.5、5.4）。"""
        # 步骤 1：置为「解析中」，供前端展示解析进度（PRD 5.4 解析状态）
        attachment.parse_status = AttachmentParseStatus.PARSING
        # 步骤 2：交 A2 执行解析；解析产物与 attachment_status 消息均由 A2 产出（PRD 20.2、20.4 L5~L7）
        result = self.parser.run(attachment)
        # 步骤 3：按解析结果回写解析状态——失败可重试、达标为成功、低置信度转人工（PRD 5.4、20.1 P5）
        if result is None:
            attachment.parse_status = AttachmentParseStatus.FAILED       # 解析未产出结果，允许重试
        elif (result.confidence or 0.0) >= CONFIDENCE_THRESHOLD:
            attachment.parse_status = AttachmentParseStatus.SUCCEEDED    # 置信度达标
        else:
            attachment.parse_status = AttachmentParseStatus.MANUAL_REVIEW  # 低置信度转人工复核
        # 步骤 4：返回解析结果（失败时为 None），供环节四聚合研判
        return result
