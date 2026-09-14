"""A2 凭证解析智能体主流程（PRD 20.2）。

职责：PDF / PNG / JPG 解析、OCR、文档分类、关键字段提取、原文证据定位、置信度评估。
输出：全文文本、字段提取结果、字段级证据位置（页码 + 归一化坐标 + 置信度 + 原文片段）。
边界：不做金额合规判断、不给风险等级、不修改单据结构化字段、不判定发票真伪（PRD 2.7.1）。
"""

from datetime import datetime, timezone  # 解析完成时间

import json  # 字段映射的序列化（作为大模型提示词的一部分）

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
        self.category_confidence = 0.0  # 分类环节反馈的置信度（PRD 20.4 L5）

    def run(self, attachment: DocumentAttachment) -> AttachmentParseResult | None:
        """主流程：校验附件 → 提取文本 → 文档分类 → 字段抽取 → 证据定位 → 标注解析状态。"""
        self.attachment = attachment
        if not self.step1_validate_attachment():
            return None  # 格式或路径不合规，不再继续解析（PRD 5.4）
        self.pages = self.step2_extract_text()
        if self.pages is None:
            # 文本提取失败（文件损坏、OCR 引擎不可用等）：标记失败并推送失败环节，允许重试
            # 依据 PRD 5.4 解析状态管理与 PRD 8.1 第 9 条「展示失败环节并允许重试」
            self.attachment.parse_status = AttachmentParseStatus.FAILED
            self.publisher.attachment_status(self.attachment.id, self.attachment.storage_status,
                                             AttachmentParseStatus.FAILED.value)
            self.publisher.error(0, "TEXT_EXTRACTION_FAILED",
                                 "附件文本提取失败，请检查文件完整性或 OCR 运行环境后重试")
            return None
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

    def step2_extract_text(self) -> list[str] | None:
        """按页提取文本：PDF 用 pypdf，图片用 OCR；页码由本步按顺序记录（确定性，不交大模型）。

        提取失败（文件损坏、OCR 引擎未安装或不可用等）时返回 None，由主流程标记解析失败并允许重试
        （PRD 5.4 解析状态、PRD 8.1 第 9 条）。
        """
        try:
            # 步骤 1：PDF 走文本层提取，图片走 OCR；两者均按页返回，页码即列表下标 + 1
            if (self.attachment.file_type or "").upper() == "PDF":
                return [page.extract_text() or ""
                        for page in PdfReader(self.attachment.file_path).pages]
            return [pytesseract.image_to_string(Image.open(self.attachment.file_path))]
        except Exception:
            # 步骤 2：任何提取层面的异常都归为「解析失败」，不向上抛出中断整条分析链路
            return None

    def step3_classify_document(self) -> str:
        """【大模型 L5】文档分类：发票 / 合同 / 行程单 / 付款依据 / 费用明细（PRD 20.4 L5）。"""
        result = self.llm.extract(
            "判断文档类别（发票/合同/行程单/付款依据/费用明细），以 JSON 对象返回，"
            '形如 {"category": "...", "confidence": 0.95}：\n' + self.pages[0][:2000])
        # 记录分类环节反馈的置信度，供解析状态判定使用（PRD 20.1 P5 低置信度转人工复核）
        self.category_confidence = float(result.get("confidence") or 0.0)
        return result.get("category") or ""

    def step4_extract_fields(self) -> dict:
        """【大模型 L6】抽取关键字段并建议统一格式（发票代码、号码、金额、日期、销售方等）。

        要求模型以 JSON 对象返回（键为 fields 时取其内容，否则取整个对象），
        保证产物始终是「字段名 → 取值」的映射，便于落库与证据定位（PRD 5.4）。
        """
        result = self.llm.extract(
            "抽取以下文档的关键字段，以 JSON 对象返回，键为 fields、值为「字段名: 取值」的映射；"
            "金额与日期按 YYYY-MM-DD 与纯数字格式给出：\n" + "\n".join(self.pages)[:4000])
        fields = result.get("fields") if isinstance(result.get("fields"), dict) else result
        return fields if isinstance(fields, dict) else {}

    def step5_locate_evidence(self) -> list[dict]:
        """【大模型 L7】为每个字段定位证据：页码、归一化坐标、置信度与原文片段（PRD 12.3 G10）。"""
        result = self.llm.extract(
            "为以下字段输出所在页码 page_no、归一化坐标 bbox（x0/y0/x1/y1，取值 0~1）、"
            "置信度 confidence（0~1）与原文片段 evidence_text，以 JSON 对象返回，键为 positions"
            "（值为数组）：\n" + json.dumps(self.fields, ensure_ascii=False))
        positions = result.get("positions")
        return positions if isinstance(positions, list) else []

    def step6_mark_parse_status(self) -> AttachmentParseResult:
        """按 PRD 5.4 以 0.8 为阈值标注解析状态，并返回解析结果（仅组装，不做合规判断）。"""
        # 步骤 1：过滤出结构完整的证据位置——大模型输出格式不稳定，
        #         缺字段名或坐标不齐的元素一律丢弃，只保留可定位、可溯源的证据（PRD 12.3 G10）
        positions: list[EvidencePosition] = []
        for item in self.positions:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if not item.get("field_name") or not isinstance(bbox, dict):
                continue
            if not {"x0", "y0", "x1", "y1"} <= set(bbox):
                continue
            positions.append(EvidencePosition(
                field_name=str(item["field_name"]),
                page_no=int(item.get("page_no") or 1),
                bbox=BBox(**{name: float(bbox[name]) for name in ("x0", "y0", "x1", "y1")}),
                confidence=float(item.get("confidence") or 0.0),
                evidence_text=item.get("evidence_text")))
        # 步骤 2：整体置信度取「分类环节反馈的置信度」与「字段级位置置信度」中的最低值；
        #         两者均无有效反馈时才为 0。避免因模型未给出坐标就把整份解析一律降级（PRD 20.1 P5）
        candidates = [self.category_confidence] + [p.confidence for p in positions]
        candidates = [value for value in candidates if value > 0]
        confidence = min(candidates) if candidates else 0.0
        status = (AttachmentParseStatus.SUCCEEDED if confidence >= CONFIDENCE_THRESHOLD
                  else AttachmentParseStatus.MANUAL_REVIEW)  # 低置信度转人工复核（PRD 20.1 P5）
        self.publisher.attachment_status(self.attachment.id, self.attachment.storage_status,
                                         status.value)
        # 步骤 3：组装解析结果返回（主键待落库后回填，故以 0 占位）
        return AttachmentParseResult(id=0,
                                     attachment_id=self.attachment.id,
                                     document_category=self.category,
                                     full_text="\n".join(self.pages), fields_json=self.fields,
                                     evidence_positions_json=positions, confidence=confidence,
                                     created_at=datetime.now(timezone.utc))
