"""R01~R04 金额与一致性类规则（PRD 9.1）。

| 编码 | 规则 | 输出（PRD 9.1） |
|---|---|---|
| R01 | 单据与发票金额一致性 | 差异金额、差异比例 |
| R02 | 明细与总金额一致性 | 合计差异、可疑明细行 |
| R03 | 合同与付款一致性 | 不一致项清单 |
| R04 | 批量付款一致性 | 差异项、重复账号 / 重复付款 |

边界（PRD 20.1 P1、20.4 L8）：本模块只做**确定性**的金额聚合、精确比对与容差判定；
主体名称、付款条件等跨来源的**语义**一致性由 A3 的大模型环节（L8）承担，本模块只给精确比对结果。
"""

from collections import Counter  # Counter：统计重复明细行与重复收款
from decimal import Decimal  # Decimal：金额与比例，禁止 float 以免精度丢失
from typing import Any  # Any：附件解析字段的取值类型不固定

from engine.rule_support import (  # 规则引擎公共件
    KEY_TOLERANCE, as_decimal, build_result, find_rule, params_of, to_ratio_text, to_text,
)
from schema.enums import DocumentType  # 单据类型：R04 仅对批量付款单适用
from schema.tables_document import (  # 单据、明细、附件解析结果、发票记录
    AttachmentParseResult, DocumentLineItem, FinancialDocument, InvoiceRecord,
)
from schema.tables_rules import ReviewRule  # 规则配置：阈值的唯一来源

__all__ = ["AmountRules", "R01_INVOICE", "R02_TOTAL", "R03_CONTRACT", "R04_BATCH"]

# 本模块实现的规则编码（PRD 9.1）
R01_INVOICE = "R01"    # 单据与发票金额一致性
R02_TOTAL = "R02"      # 明细与总金额一致性
R03_CONTRACT = "R03"   # 合同与付款一致性
R04_BATCH = "R04"      # 批量付款一致性

# R03 从合同附件的 fields_json 里读取的键名候选——A2 的抽取键名 PRD 未列举，故在此集中声明，
# 命中任一即取值；日后与 A2 的提示词对齐时只需改这一处
CONTRACT_AMOUNT_KEYS = ("contract_amount", "total_amount", "amount")
CONTRACT_SELLER_KEYS = ("supplier_name", "seller_name", "party_b")
CONTRACT_TERMS_KEYS = ("payment_terms", "payment_condition")
CONTRACT_RATIO_KEYS = ("payment_ratio", "ratio")
# 合同类附件的文档分类取值（PRD 5.4 列举的五类附件之一）
CONTRACT_CATEGORY = "合同"


class AmountRules:
    """R01~R04：金额与一致性类规则（PRD 9.1）。"""

    def __init__(self, rules: list[ReviewRule]) -> None:
        """保存规则配置表；每条规则执行前按编码取自己的阈值（PRD 12.3 G07）。"""
        # 步骤 1：持有规则表，各规则据此取阈值与等级档位
        self.rules = rules

    def check_invoice_consistency(self, document: FinancialDocument,
                                  invoices: list[InvoiceRecord]) -> list[dict]:
        """R01：对比单据金额与发票含税金额合计，超过金额容差即命中（PRD 9.1 R01）。"""
        # 步骤 1：取规则配置；未配置则本规则整体跳过，不臆造容差（PRD 20.7）
        rule = find_rule(self.rules, R01_INVOICE)
        if rule is None:
            return []
        # 步骤 2：算发票含税金额合计——金额缺失的发票行按 0 计，保证合计可算（确定性求和）
        invoice_total = sum((i.amount_including_tax or Decimal(0) for i in invoices), Decimal(0))
        # 步骤 3：取单据侧金额——优先「支出金额（本次支出 / 报销金额）」，缺失时退回「总金额」（PRD 5.2）
        document_amount = document.amount if document.amount is not None else document.total_amount
        if document_amount is None:
            return []  # 无对比基准，不做判定
        # 步骤 4：算差异金额与差异比例（PRD 9.1 R01 要求输出这两项）
        difference = invoice_total - document_amount
        ratio = abs(difference) / document_amount if document_amount else None
        # 步骤 5：容差判定——差异绝对值未超过容差即未命中；容差取自规则参数（PRD 9.3 示例键名）
        tolerance = as_decimal(params_of(rule).get(KEY_TOLERANCE)) or Decimal(0)
        if abs(difference) <= tolerance:
            return []
        # 步骤 6：组装命中结果——计算值取发票合计与差异，对比值取单据金额，来源给出发票主键（PRD 9.3）
        return [build_result(rule, "单据金额与发票合计差异 %s" % abs(difference), ratio=ratio,
                             actual={"invoice_total": str(invoice_total),
                                     "difference": str(difference),
                                     "difference_ratio": to_ratio_text(ratio)},
                             reference={"document_amount": str(document_amount)},
                             evidence={"document_id": document.id,
                                       "invoice_ids": [i.id for i in invoices]})]

    def check_line_items_total(self, document: FinancialDocument,
                               line_items: list[DocumentLineItem]) -> list[dict]:
        """R02：计算明细合计并与单据总金额对比，识别漏项与重复项（PRD 9.1 R02）。"""
        # 步骤 1：取规则配置与比对基准；总金额缺失则不做判定
        rule = find_rule(self.rules, R02_TOTAL)
        if rule is None or document.total_amount is None:
            return []
        # 步骤 2：算明细合计（确定性求和；金额缺失的明细行按 0 计）
        line_total = sum((item.amount or Decimal(0) for item in line_items), Decimal(0))
        # 步骤 3：算合计差异与偏离比例——合计小于总金额即属「漏项」方向
        difference = line_total - document.total_amount
        ratio = abs(difference) / document.total_amount if document.total_amount else None
        # 步骤 4：识别重复项——「名称 + 金额 + 消费日期」三者完全相同的行计为重复（PRD 9.1 R02）
        counted = Counter((item.item_name, item.amount, item.expense_date) for item in line_items)
        # 步骤 5：容差判定——差异未超容差且无重复项时未命中
        tolerance = as_decimal(params_of(rule).get(KEY_TOLERANCE)) or Decimal(0)
        if abs(difference) <= tolerance and not any(n > 1 for n in counted.values()):
            return []
        # 步骤 6：整理可疑明细行（重复项）——保留重复次数，供人工定位
        suspicious = [{"item_name": key[0],
                       "amount": None if key[1] is None else str(key[1]),
                       "expense_date": None if key[2] is None else key[2].isoformat(),
                       "occurrences": count}
                      for key, count in counted.items() if count > 1]
        # 步骤 7：组装结果——计算值取明细合计与差异，对比值取单据总金额（PRD 9.3）
        return [build_result(rule, "明细合计与总金额差异 %s" % abs(difference), ratio=ratio,
                             actual={"line_item_total": str(line_total),
                                     "difference": str(difference),
                                     "difference_ratio": to_ratio_text(ratio)},
                             reference={"document_amount": str(document.total_amount)},
                             evidence={"document_id": document.id,
                                       "line_item_ids": [i.id for i in line_items],
                                       "duplicated_lines": suspicious})]

    def check_contract_payment(self, document: FinancialDocument,
                               parse_results: list[AttachmentParseResult]) -> list[dict]:
        """R03：逐项比对合同主体、合同金额、付款条件与付款比例（PRD 9.1 R03）。"""
        # 步骤 1：取规则配置；未配置则跳过
        rule = find_rule(self.rules, R03_CONTRACT)
        if rule is None:
            return []
        # 步骤 2：取合同附件的解析字段；无合同附件或未抽到字段即数据不足，不产出风险项（PRD 20.7）
        fields = self._contract_fields(parse_results)
        if not fields:
            return []
        # 步骤 3：逐项比对，收集不一致项（精确比对；语义差异交 A3 的 L8，PRD 20.4 L8）
        mismatches: list[dict] = []
        # 步骤 3.1：合同主体 vs 单据上的供应商名称
        seller = self._first(fields, CONTRACT_SELLER_KEYS)
        if seller and document.supplier_name and to_text(seller) != to_text(document.supplier_name):
            mismatches.append({"item": "合同主体", "contract": to_text(seller),
                               "document": to_text(document.supplier_name)})
        # 步骤 3.2：合同金额 × 付款比例 vs 本次付款金额（比例或合同金额缺失时不判）
        contract_amount = as_decimal(self._first(fields, CONTRACT_AMOUNT_KEYS))
        expected = None
        if contract_amount is not None and document.payment_ratio is not None:
            expected = contract_amount * document.payment_ratio
            paid = document.amount if document.amount is not None else document.total_amount
            tolerance = as_decimal(params_of(rule).get(KEY_TOLERANCE)) or Decimal(0)
            if paid is not None and abs(paid - expected) > tolerance:
                mismatches.append({"item": "合同金额×付款比例与付款金额",
                                   "contract": str(expected), "document": str(paid)})
        # 步骤 3.3：付款条件——合同字段与单据付款条件做精确比对
        terms = self._first(fields, CONTRACT_TERMS_KEYS)
        if terms and document.payment_terms and to_text(terms) != to_text(document.payment_terms):
            mismatches.append({"item": "付款条件", "contract": to_text(terms),
                               "document": to_text(document.payment_terms)})
        # 步骤 3.4：付款比例——合同字段给出比例时与单据比例比对
        contract_ratio = as_decimal(self._first(fields, CONTRACT_RATIO_KEYS))
        if (contract_ratio is not None and document.payment_ratio is not None
                and contract_ratio != document.payment_ratio):
            mismatches.append({"item": "付款比例", "contract": str(contract_ratio),
                               "document": str(document.payment_ratio)})
        # 步骤 4：无不一致项即未命中（PRD 9.1 R03 的输出为不一致项清单）
        if not mismatches:
            return []
        # 步骤 5：组装结果——不一致项清单作为计算值，证据给出合同附件的字段级位置（PRD 9.3）
        return [build_result(rule, "合同与付款信息存在 %d 项不一致" % len(mismatches),
                             actual={"mismatches": mismatches},
                             reference={"contract_amount": None if contract_amount is None
                                        else str(contract_amount),
                                        "expected_payment": None if expected is None
                                        else str(expected)},
                             evidence=self._contract_evidence(parse_results))]

    def check_batch_payment(self, document: FinancialDocument,
                            line_items: list[DocumentLineItem]) -> list[dict]:
        """R04：比对付款笔数、各笔金额合计与批次总金额，并识别重复收款（PRD 9.1 R04）。

        笔数与合计的判据与 PRD 5.3 的字段级约束一致——该约束的校验时机本就包含「风险分析」，
        故本规则与提交校验同源但不重复：前者在提交时拦截，后者在分析时产出风险项。
        """
        # 步骤 1：仅批量付款单适用，其余单据类型直接返回（PRD 5.1）
        if document.document_type is not DocumentType.BATCH_PAYMENT:
            return []
        # 步骤 2：取规则配置；未配置则跳过
        rule = find_rule(self.rules, R04_BATCH)
        if rule is None:
            return []
        # 步骤 3：收齐差异项——付款笔数须等于付款明细行数（PRD 5.3）
        mismatches: list[dict] = []
        if document.payment_count is not None and document.payment_count != len(line_items):
            mismatches.append({"item": "付款笔数", "declared": str(document.payment_count),
                               "actual": str(len(line_items))})
        # 步骤 4：各笔金额合计须等于批次总金额（PRD 5.3）
        line_total = sum((item.amount or Decimal(0) for item in line_items), Decimal(0))
        if document.batch_total_amount is not None and line_total != document.batch_total_amount:
            mismatches.append({"item": "单笔金额合计",
                               "declared": str(document.batch_total_amount),
                               "actual": str(line_total)})
        # 步骤 5：识别重复收款——同批次内相同收款账号，或相同「账号 + 金额」（PRD 9.1 R04）
        by_account = Counter(to_text(i.payee_account) for i in line_items if i.payee_account)
        by_pair = Counter((to_text(i.payee_account), i.amount)
                          for i in line_items if i.payee_account)
        repeated_accounts = sorted(a for a, n in by_account.items() if n > 1)
        repeated_payments = [{"payee_account": key[0],
                              "amount": None if key[1] is None else str(key[1]),
                              "occurrences": count}
                             for key, count in by_pair.items() if count > 1]
        # 步骤 6：三类信号都未命中则不出风险项
        if not mismatches and not repeated_accounts and not repeated_payments:
            return []
        # 步骤 7：组装结果——差异项与重复收款（PRD 9.1 R04 的输出）
        return [build_result(rule, "批量付款存在差异或重复收款",
                             actual={"mismatches": mismatches,
                                     "repeated_accounts": repeated_accounts,
                                     "repeated_payments": repeated_payments},
                             reference={"batch_total_amount":
                                        None if document.batch_total_amount is None
                                        else str(document.batch_total_amount),
                                        "payment_count": document.payment_count},
                             evidence={"document_id": document.id,
                                       "line_item_ids": [i.id for i in line_items]})]

    @staticmethod
    def _contract_fields(parse_results: list[AttachmentParseResult]) -> dict[str, Any]:
        """从附件解析结果中取「合同」类文档的字段提取结果；取不到时返回空字典。"""
        # 步骤 1：按文档分类筛出合同附件（分类取值见 PRD 5.4 的五类附件）
        for result in parse_results:
            if to_text(result.document_category) == CONTRACT_CATEGORY:
                # 步骤 2：返回其字段提取结果；为空则视为未抽到字段
                return result.fields_json or {}
        # 步骤 3：无合同附件即返回空字典，由调用方判定数据不足
        return {}

    @staticmethod
    def _first(fields: dict[str, Any], keys: tuple[str, ...]) -> Any:
        """按候选键名依次取值，返回首个非空值；全空返回 None。"""
        # 步骤 1：按候选顺序试探键名——A2 的抽取键名 PRD 未列举，故允许候选
        for key in keys:
            if fields.get(key) not in (None, ""):
                return fields[key]
        # 步骤 2：全部未命中返回 None，由调用方判定该子项不做比对
        return None

    @staticmethod
    def _contract_evidence(parse_results: list[AttachmentParseResult]) -> dict:
        """给出合同附件的证据来源：附件主键、页码、原文片段与置信度（PRD 9.3 数据来源）。"""
        # 步骤 1：找到合同附件及其解析结果
        for result in parse_results:
            if to_text(result.document_category) == CONTRACT_CATEGORY:
                # 步骤 2：取字段级证据位置（页码 / 归一化坐标 / 原文片段 / 置信度，PRD 12.3 G10）
                positions = result.evidence_positions_json or []
                return {"attachment_id": result.attachment_id,
                        "confidence": result.confidence,
                        "positions": [{"field_name": p.field_name, "page_no": p.page_no,
                                       "evidence_text": p.evidence_text,
                                       "confidence": p.confidence} for p in positions]}
        # 步骤 3：无合同附件解析结果时只回附件维度可用的信息
        return {}
