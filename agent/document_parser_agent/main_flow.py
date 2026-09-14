"""A2 凭证解析智能体主流程（PRD 20.2）。

职责：PDF / PNG / JPG 解析、OCR、文档分类、关键字段提取、原文证据定位、置信度评估。
输出：全文文本、字段提取结果、字段级证据位置（页码 + 归一化坐标 + 置信度 + 原文片段）。
边界：不做金额合规判断、不给风险等级、不修改单据结构化字段、不判定发票真伪（PRD 2.7.1）。
"""

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L5~L7）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["DocumentParserAgent"]


class DocumentParserAgent:
    """A2 凭证解析智能体。"""

    def __init__(self) -> None:
        pass

    def run(self, attachment_id: int) -> None:
        """主流程：校验附件 → 提取文本 → 文档分类 → 字段抽取 → 证据定位 → 标注解析状态。"""
        self.step1_validate_attachment(attachment_id)
        self.step2_extract_text()
        self.step3_classify_document()
        self.step4_extract_fields()
        self.step5_locate_evidence()
        self.step6_mark_parse_status()

    def step1_validate_attachment(self, attachment_id: int) -> None:
        """校验附件格式、大小与页数（PDF / PNG / JPG），失败即置解析状态为 failed（PRD 2.7.1 附件能力）。"""
        pass

    def step2_extract_text(self) -> None:
        """提取全文文本与分页文本块，并记录页码（确定性逻辑，页码与坐标不交大模型）。"""
        pass

    def step3_classify_document(self) -> None:
        """【大模型 L5】文档分类：发票 / 合同 / 行程单 / 付款依据 / 费用明细（PRD 20.4 L5）。"""
        pass

    def step4_extract_fields(self) -> None:
        """【大模型 L6】抽取关键字段并做格式归一化建议（发票代码、号码、金额、日期、销售方等）。"""
        pass

    def step5_locate_evidence(self) -> None:
        """【大模型 L7】为每个字段定位证据：页码 + 归一化坐标 + 置信度 + 原文片段（PRD 12.3 G10）。"""
        pass

    def step6_mark_parse_status(self) -> None:
        """标注解析状态：低置信度置 manual_review，并推送 attachment_status（PRD 20.1 P5）。"""
        pass
