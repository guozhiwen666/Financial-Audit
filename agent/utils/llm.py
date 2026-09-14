"""大模型调用的公共封装（PRD 20.4 大模型使用点总表）。

四个智能体共用：A1 理解（L1~L4）、A2 抽取（L5~L7）、A3 归纳（L8~L10）、A4 表达（L11）。

边界（PRD 20.1 P1）：本模块只承担"理解 / 抽取 / 归纳 / 表达"四类工作；
金额计算、规则阈值判定、状态流转、风险等级取值、权限校验一律不经由此处。
"""

import json  # 解析结构化抽取的返回

from openai import OpenAI  # 已声明依赖（pyproject.toml）

from config.config import llm_config  # 大模型配置（config/config.py，导入时加载 .env）

__all__ = ["LLMClient"]


class LLMClient:
    """大模型调用客户端：统一入口，便于集中管理模型配置与置信度。"""

    def __init__(self, model: str) -> None:
        # 模型名由调用方从系统参数注入（PRD 2.7.9「模型配置」由系统管理员维护），本模块不设默认值；
        # 地址与凭据统一取自 config，避免代码中存放密钥、也避免依赖调用进程是否已加载 .env
        self.model = model
        self.client = OpenAI(base_url=llm_config.base_url, api_key=llm_config.api_key)

    def complete(self, prompt: str) -> str:
        """文本生成：风险描述、业务归因、处理建议与报告正文等表达类任务（L9、L11）。"""
        reply = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}])
        return reply.choices[0].message.content or ""

    def extract(self, prompt: str) -> dict:
        """结构化抽取：槽位抽取、文档分类、关键字段提取（L1、L3、L5、L6），返回 JSON 对象。

        契约保证：一律返回字典。模型偶尔会返回 JSON 数组或标量，此时返回空字典，
        由调用方按「缺省」处理——避免把类型异常抛进确定性流程（PRD 20.1 P1）。
        """
        reply = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"})
        data = json.loads(reply.choices[0].message.content or "{}")
        return data if isinstance(data, dict) else {}

    def confidence(self, result: dict) -> float:
        """取产出携带的识别置信度（0~1），供低置信度转人工复核的阈值判定（PRD 20.1 P5）。"""
        return float(result.get("confidence") or 0.0)
