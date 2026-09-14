"""大模型调用的公共封装（PRD 20.4 大模型使用点总表）。

四个智能体共用：A1 理解（L1~L4）、A2 抽取（L5~L7）、A3 归纳（L8~L10）、A4 表达（L11）。

边界（PRD 20.1 P1）：本模块只承担"理解 / 抽取 / 归纳 / 表达"四类工作；
金额计算、规则阈值判定、状态流转、风险等级取值、权限校验一律不经由此处。
"""

__all__ = ["LLMClient"]


class LLMClient:
    """大模型调用客户端：统一入口，便于集中管理模型配置与置信度。"""

    def __init__(self) -> None:
        pass

    def complete(self, prompt: str) -> str:
        """文本生成：用于风险描述、业务归因、处理建议与报告正文等表达类任务（L9、L11）。"""
        pass

    def extract(self, prompt: str) -> dict:
        """结构化抽取：用于槽位抽取、文档分类、关键字段提取等（L1、L3、L5、L6）。"""
        pass

    def confidence(self, result: dict) -> float:
        """返回本次产出的识别置信度 0~1，供低置信度转人工复核的阈值判定（PRD 20.1 P5）。"""
        pass
