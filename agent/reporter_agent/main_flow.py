"""A4 报告与留痕智能体主流程（PRD 20.2）。

职责：把风险结论渲染为报告正文与面板数据、导出 Markdown / PDF / HTML、
归档人工复核结果、触发操作审计留痕。
边界：不新增或删除风险项、不改风险等级与处理建议、不改写已提交的复核与审批记录
（留痕只可追加，不可修改或删除，PRD 20.1 P7）。
"""

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L11）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["ReporterAgent"]


class ReporterAgent:
    """A4 报告与留痕智能体。"""

    def __init__(self) -> None:
        pass

    def run(self, task_id: int, fmt: str = "markdown") -> None:
        """主流程：载入结论 → 生成面板 → 撰写正文 → 导出报告 → 归档复核 → 写审计留痕。"""
        self.step1_load_findings(task_id)
        self.step2_build_panels()
        self.step3_write_report()
        self.step4_export_report(fmt)
        self.step5_archive_review()
        self.step6_write_audit_log()

    def step1_load_findings(self, task_id: int) -> None:
        """载入风险项、整体风险等级与处理建议（只读，不得增删或改写，PRD 20.2 边界）。"""
        pass

    def step2_build_panels(self) -> None:
        """生成面板数据：风险分类统计与金额核对（五口径对照及差异），均为确定性计算。"""
        pass

    def step3_write_report(self) -> None:
        """【大模型 L11】按 PRD 第 15 章章节结构撰写报告正文（含单据摘要、整体风险、证据列表）。"""
        pass

    def step4_export_report(self, fmt: str) -> None:
        """导出报告，格式支持 markdown / pdf / html（PRD 13.10 通用约定）。"""
        pass

    def step5_archive_review(self) -> None:
        """归档人工复核意见与审批结果；已提交记录只可追加，不得改写（PRD 2.7.14 安全边界）。"""
        pass

    def step6_write_audit_log(self) -> None:
        """写入操作审计留痕：操作人、操作时间、变更内容，缺一不可（PRD 2.7.14、3.3）。"""
        pass
