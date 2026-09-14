"""最外层主流程（PRD 2.7.1 / 第 7 章）。

PRD 2.7.1 定义本系统覆盖七个环节：单据创建、附件管理、审批流转、风险分析、人工复核、报告导出、操作审计；
PRD 1.2 将其归纳为「录入 → 解析 → 分析 → 审批 → 留痕」的闭环；
PRD 第 7 章给出主流程与单据状态流转。

本模块只定义最外层主流程的类骨架，方法一律不实现（pass）。
"""

from langgraph.graph import StateGraph

__all__ = [
    "MainFlow",
    "DocumentCreationFlow",
    "AttachmentFlow",
    "ApprovalFlow",
    "RiskAnalysisFlow",
    "ManualReviewFlow",
    "ReportExportFlow",
    "AuditLogFlow",
]


class MainFlow:
    """最外层主流程：装配七个环节并驱动其状态流转（PRD 2.7.1、7.1、7.3）。"""

    def build_graph(self) -> StateGraph:
        """装配主流程：单据创建 → 附件管理 → 审批流转 → 风险分析 → 人工复核 → 报告导出 → 操作审计。"""
        pass

    def run(self, document_id: int) -> None:
        """从单据提交开始执行一次完整主流程（PRD 7.1）。"""
        pass

    def resume(self, document_id: int) -> None:
        """退回后重新提交：生成新版本与新的分析任务（PRD 7.2）。"""
        pass


class DocumentCreationFlow:
    """环节一 单据创建（PRD 2.7.1 单据能力、7.3）。"""

    def create(self, document_type: str) -> int:
        """创建单据草稿，返回单据主键。"""
        pass

    def update(self, document_id: int) -> None:
        """编辑草稿或退回状态的单据。"""
        pass

    def copy(self, document_id: int) -> int:
        """复制单据并生成新草稿，返回新单据主键。"""
        pass

    def submit(self, document_id: int) -> None:
        """提交单据：生成单据快照、审批实例与首个审批任务（PRD 7.2）。"""
        pass

    def withdraw(self, document_id: int) -> None:
        """撤回未处理的单据。"""
        pass

    def void(self, document_id: int) -> None:
        """作废符合条件的单据。"""
        pass


class AttachmentFlow:
    """环节二 附件管理（PRD 2.7.1 附件能力、解析能力）。"""

    def upload(self, document_id: int, file_name: str) -> int:
        """上传附件并做格式校验（PDF / PNG / JPG），返回附件主键。"""
        pass

    def parse(self, attachment_id: int) -> None:
        """创建附件解析任务：OCR、字段提取与原文证据定位。"""
        pass


class ApprovalFlow:
    """环节三 审批流转（PRD 2.7.1 审批能力、7.3）。"""

    def approve(self, document_id: int) -> None:
        """通过当前审批节点；末节点通过后单据状态变为已通过。"""
        pass

    def return_back(self, document_id: int) -> None:
        """退回单据，允许申请人修改后重新提交。"""
        pass

    def reject(self, document_id: int) -> None:
        """驳回单据。"""
        pass


class RiskAnalysisFlow:
    """环节四 风险分析（PRD 2.7.1 分析能力、9.1）。"""

    def analyze(self, document_id: int) -> None:
        """创建风险分析任务：聚合单据、明细、附件解析结果、规则、市场价与供应商资料。"""
        pass

    def compare_amounts(self, document_id: int) -> None:
        """金额核对：单据总金额、明细合计、发票合计、合同金额、付款金额对照。"""
        pass


class ManualReviewFlow:
    """环节五 人工复核（PRD 2.7.1、6.2.8）。"""

    def review_finding(self, finding_id: int) -> None:
        """更新风险项的人工复核状态。"""
        pass

    def submit_conclusion(self, report_id: int) -> None:
        """提交人工复核意见与审批结果。"""
        pass


class ReportExportFlow:
    """环节六 报告导出（PRD 2.7.1、第 15 章）。"""

    def generate(self, document_id: int) -> int:
        """生成风险审核报告，返回报告主键。"""
        pass

    def export(self, report_id: int, fmt: str) -> None:
        """导出报告，格式支持 markdown / pdf / html（PRD 13.10）。"""
        pass


class AuditLogFlow:
    """环节七 操作审计（PRD 2.7.1、2.7.14）。"""

    def record(self, action_type: str, resource_id: int) -> None:
        """记录操作审计：接口调用、附件访问、规则变更、分析任务、审批操作。"""
        pass
