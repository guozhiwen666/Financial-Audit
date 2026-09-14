"""A2 凭证解析智能体主流程（PRD 20.2）。

职责：PDF / PNG / JPG 解析、OCR、文档分类、关键字段提取、原文证据定位、置信度评估。
输出：全文文本、字段提取结果、字段级证据位置（页码 + 归一化坐标 + 置信度 + 原文片段）。
边界：不做金额合规判断、不给风险等级、不修改单据结构化字段、不判定发票真伪（PRD 2.7.1）。
"""

from datetime import datetime, timezone  # 解析完成时间

import pytesseract  # 图片 OCR（已声明依赖；需系统安装 tesseract 可执行文件）
from PIL import Image  # 打开图片交给 OCR（已声明依赖）
from pypdf import PdfReader  # PDF 文本提取（已声明依赖）

from schema.enums import AttachmentParseStatus  # 解析状态（PRD 2.7.12）
from schema.tables_document import AttachmentParseResult, BBox, DocumentAttachment, EvidencePosition

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L5~L7）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["DocumentParserAgent"]

# PRD 5.4：附件仅支持这三种格式；PRD 5.4 亦规定置信度低于 0.8 转人工复核
SUPPORTED_FORMATS = ("PDF", "PNG", "JPG")
CONFIDENCE_THRESHOLD = 0.8


class DocumentParserAgent:
    """A2 凭证解析智能体。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        self.llm = llm
        self.publisher = publisher
        self.pages: list[str] = []  # 分页文本，下标即页码 - 1

    def run(self, attachment: DocumentAttachment) -> AttachmentParseResult | None:
        """主流程：校验附件 → 提取文本 → 文档分类 → 字段抽取 → 证据定位 → 标注解析状态。"""
        self.attachment = attachment
        if not self.step1_validate_attachment():
            return None  # 格式或页数不合规，不再继续解析（PRD 5.4）
        self.pages = self.step2_extract_text()
        self.category = self.step3_classify_document()
        self.fields = self.step4_extract_fields()
        self.positions = self.step5_locate_evidence()
        return self.step6_mark_parse_status()

    def step1_validate_attachment(self) -> bool:
        """校验格式与文件路径（PRD 5.4、16 S4）；不合规则置 failed 并推送 attachment_status。"""
        suffix = (self.attachment.file_type or "").upper()
        valid = suffix in SUPPORTED_FORMATS and bool(self.attachment.file_path)
        self.publisher.attachment_status(
            self.attachment.id, self.attachment.storage_status,
            (AttachmentParseStatus.PARSING if valid else AttachmentParseStatus.FAILED).value)
        return valid

    def step2_extract_text(self) -> list[str]:
        """按页提取文本：PDF 用 pypdf，图片用 OCR；页码由本步按顺序记录（确定性，不交大模型）。"""
        if (self.attachment.file_type or "").upper() == "PDF":
            return [page.extract_text() or "" for page in PdfReader(self.attachment.file_path).pages]
        return [pytesseract.image_to_string(Image.open(self.attachment.file_path))]

    def step3_classify_document(self) -> str:
        """【大模型 L5】文档分类：发票 / 合同 / 行程单 / 付款依据 / 费用明细（PRD 20.4 L5）。"""
        result = self.llm.extract(
            "判断文档类别（发票/合同/行程单/付款依据/费用明细），输出 JSON："
            '{"category":..., "confidence":...}\n' + self.pages[0][:2000])
        return result.get("category") or ""

    def step4_extract_fields(self) -> dict:
        """【大模型 L6】抽取关键字段并建议统一格式（发票代码、号码、金额、日期、销售方等）。"""
        return self.llm.extract("抽取以下文档的关键字段，输出 JSON；金额与日期按统一格式给出：\n"
                                + "\n".join(self.pages)[:4000])

    def step5_locate_evidence(self) -> list[dict]:
        """【大模型 L7】为每个字段定位证据：页码、归一化坐标、置信度与原文片段（PRD 12.3 G10）。"""
        return self.llm.extract("为以下字段输出所在页码 page_no、归一化坐标 bbox、置信度 confidence "
                                "与原文片段 evidence_text，输出 JSON 数组 positions：\n"
                                + str(self.fields)).get("positions", [])

    def step6_mark_parse_status(self) -> AttachmentParseResult:
        """按 PRD 5.4 以 0.8 为阈值标注解析状态，并返回解析结果（仅组装，不做合规判断）。"""
        confidence = min((p.get("confidence") or 0.0 for p in self.positions), default=0.0)
        status = (AttachmentParseStatus.SUCCEEDED if confidence >= CONFIDENCE_THRESHOLD
                  else AttachmentParseStatus.MANUAL_REVIEW)  # 低置信度转人工复核（PRD 20.1 P5）
        self.publisher.attachment_status(self.attachment.id, self.attachment.storage_status,
                                         status.value)
        positions = [EvidencePosition(field_name=p["field_name"], page_no=p["page_no"],
                                      bbox=BBox(**p["bbox"]), confidence=p["confidence"],
                                      evidence_text=p["evidence_text"]) for p in self.positions]
        return AttachmentParseResult(id=0,  # 主键待落库后回填，故以 0 占位（schema 约定主键必填）
                                     attachment_id=self.attachment.id,
                                     document_category=self.category,
                                     full_text="\n".join(self.pages), fields_json=self.fields,
                                     evidence_positions_json=positions, confidence=confidence,
                                     created_at=datetime.now(timezone.utc))
