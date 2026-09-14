"""实时消息构造与推送的公共封装（PRD 14.2、14.3）。

九类消息由不同角色产生，但构造与推送规则一致，故统一在此供公共调用：
A1 推送 slot_required / task_status / error / done；A2 推送 attachment_status；
A3 推送 risk_finding；A4 推送 report_ready；
document_status 与 approval_status 由后端模块在状态流转时推送（PRD 20.3）。

推送要求（PRD 14.3）：消息需带时间戳与序号，保证前端可去重、可乱序重排；
长任务必须支持轮询兜底，不依赖纯推送。
"""

from datetime import datetime  # 消息时间戳（PRD 14.2 done 消息含 finished_at）

__all__ = ["MessagePublisher"]


class MessagePublisher:
    """实时消息推送器：按 PRD 14.2 定义的消息结构逐类推送。"""

    def __init__(self) -> None:
        pass

    def publish(self, message_type: str, payload: dict) -> None:
        """按消息类型推送一条实时消息（统一出口，附带时间戳与序号）。"""
        pass

    def slot_required(self, session_id: int, slot_name: str, question_text: str,
                      candidate_values: list[str]) -> None:
        """slot_required：请求用户补齐槽位，存在歧义时以候选值请其确认（A1 使用，PRD 8.1）。"""
        pass

    def task_status(self, task_id: int, task_status: str, current_step: str,
                    progress: int) -> None:
        """task_status：分析任务进度，progress 为 0~100 整数（A1 使用，PRD 14.3）。"""
        pass

    def attachment_status(self, attachment_id: int, storage_status: str,
                          parse_status: str) -> None:
        """attachment_status：附件存储与解析状态变化（A2 使用）。"""
        pass

    def risk_finding(self, task_id: int, finding_id: int, risk_type: str, risk_level: str,
                     risk_title: str) -> None:
        """risk_finding：风险项逐条推送（A3 使用，PRD 20.3）。"""
        pass

    def report_ready(self, task_id: int, report_id: int, overall_risk_level: str) -> None:
        """report_ready：报告就绪，携带整体风险等级（A4 使用）。"""
        pass

    def error(self, task_id: int, error_code: str, error_message: str) -> None:
        """error：展示失败环节并允许重试（A1、A2 使用，PRD 8.1 第 9 条）。"""
        pass

    def done(self, task_id: int, finished_at: datetime) -> None:
        """done：任务流程结束（A1 使用）。"""
        pass
