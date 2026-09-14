"""R08~R10 供应商、附件与票据类规则（PRD 9.1）。

| 编码 | 规则 | 输出（PRD 9.1） |
|---|---|---|
| R08 | 供应商风险 | 风险标签、异常记录 |
| R09 | 附件完整性 | 缺失项、低置信度字段 |
| R10 | 重复票据风险 | 重复票据、关联单据 |

边界（PRD 20.1 P1）：本模块全部为确定性比对，不调用大模型。

**取值来源约定（PRD 未列举，属本引擎与规则配置之间的接口约定，需与用户确认）**：
* ``supplier_profiles.blacklist_status`` / ``credit_status`` 的取值 PRD 未列举，故「什么取值算命中」
  由规则参数 ``blacklist_values`` / ``credit_abnormal_values`` 给出，未配置则该子项判定跳过；
* 各单据类型**必需哪些附件** PRD 未规定（5.4 只列举了五类附件），故由规则参数
  ``required_categories`` 给出必需分类清单，未配置则只做置信度与主体一致性判定；
* 供应商的关联交易、历史履约、集中付款在既有表中无对应字段，本模块不实现，避免臆造数据来源。
"""

from decimal import Decimal  # Decimal：置信度阈值比较，禁止 float

from engine.rule_support import (  # 规则引擎公共件
    as_decimal, build_result, find_rule, params_of, to_text,
)
from schema.tables_document import (  # 附件、附件解析结果、单据、明细、发票记录
    AttachmentParseResult, DocumentAttachment, DocumentLineItem, FinancialDocument, InvoiceRecord,
)
from schema.tables_reference import SupplierProfile  # 供应商档案（R08 数据来源）
from schema.tables_rules import ReviewRule  # 规则配置

__all__ = ["DocumentRules", "R08_SUPPLIER", "R09_ATTACHMENT", "R10_DUPLICATE_INVOICE"]

# 本模块实现的规则编码（PRD 9.1）
R08_SUPPLIER = "R08"           # 供应商风险
R09_ATTACHMENT = "R09"         # 附件完整性
R10_DUPLICATE_INVOICE = "R10"  # 重复票据风险

# R08 / R09 / R10 的配置键名（PRD 未列举，属本引擎与规则配置之间的接口约定）
KEY_BLACKLIST_VALUES = "blacklist_values"          # 视为「命中黑名单」的取值清单
KEY_CREDIT_VALUES = "credit_abnormal_values"       # 视为「资质异常」的取值清单
KEY_REQUIRED_CATEGORIES = "required_categories"    # 必需附件分类清单
KEY_LOW_CONFIDENCE = "low_confidence_threshold"    # 低置信度阈值

# 附件解析置信度的默认阈值——PRD 5.4：低于 0.8 标记为待人工复核
DEFAULT_LOW_CONFIDENCE = Decimal("0.8")
# 发票类附件的文档分类取值（PRD 5.4 列举的五类附件之一）
INVOICE_CATEGORY = "发票"


class DocumentRules:
    """R08~R10：供应商、附件与票据类规则（PRD 9.1）。"""

    def __init__(self, rules: list[ReviewRule]) -> None:
        """保存规则配置表；各规则按编码取自己的阈值与取值清单（PRD 12.3 G07）。"""
        # 步骤 1：持有规则表，各规则据此取阈值与等级档位
        self.rules = rules

    def check_supplier_risk(self, document: FinancialDocument, line_items: list[DocumentLineItem],
                            supplier: SupplierProfile | None) -> list[dict]:
        """R08：识别供应商黑名单、资质异常、风险标签与收款账号变更（PRD 9.1 R08）。"""
        # 步骤 1：取规则配置；未配置或无供应商档案则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R08_SUPPLIER)
        if rule is None or supplier is None:
            return []
        params = params_of(rule)
        # 步骤 2：收集异常记录——每类信号命中即记一条，携带原始取值便于人工核对
        signals: list[dict] = []
        # 步骤 2.1：黑名单——命中取值由规则参数给出（该列取值 PRD 未列举，故不硬编码）
        blacklist_values = {to_text(v) for v in (params.get(KEY_BLACKLIST_VALUES) or [])}
        if supplier.blacklist_status and to_text(supplier.blacklist_status) in blacklist_values:
            signals.append({"signal": "供应商黑名单", "value": to_text(supplier.blacklist_status)})
        # 步骤 2.2：资质异常——同上，命中取值由规则参数给出
        credit_values = {to_text(v) for v in (params.get(KEY_CREDIT_VALUES) or [])}
        if supplier.credit_status and to_text(supplier.credit_status) in credit_values:
            signals.append({"signal": "资质异常", "value": to_text(supplier.credit_status)})
        # 步骤 2.3：风险标签——标签集合非空即产出（PRD 9.1 R08 的输出含风险标签）
        if supplier.risk_tags_json:
            signals.append({"signal": "风险标签", "value": supplier.risk_tags_json})
        # 步骤 2.4：收款账号变更——单据/明细的收款账号不在供应商已知账号集合内
        unknown = self._unknown_accounts(document, line_items, supplier)
        if unknown:
            signals.append({"signal": "收款账号变更", "value": unknown})
        # 步骤 3：无信号则未命中
        if not signals:
            return []
        # 步骤 4：组装结果——命中信号与原始取值（PRD 9.1 R08 的输出为风险标签、异常记录）
        return [build_result(rule, "供应商存在 %d 项风险信号" % len(signals),
                             actual={"signals": signals},
                             reference={"supplier_code": supplier.supplier_code,
                                        "supplier_name": supplier.supplier_name},
                             evidence={"document_id": document.id,
                                       "supplier_id": supplier.id})]

    def check_attachment_completeness(self, document: FinancialDocument,
                                      attachments: list[DocumentAttachment],
                                      parse_results: list[AttachmentParseResult]) -> list[dict]:
        """R09：检查必需附件、解析置信度与单据主体一致性（PRD 9.1 R09）。"""
        # 步骤 1：取规则配置；未配置则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R09_ATTACHMENT)
        if rule is None:
            return []
        params = params_of(rule)
        # 步骤 2：收集缺失项与低置信度字段
        missing: list[str] = []
        low_confidence: list[dict] = []
        # 步骤 2.1：无任何附件即缺失全部必需分类
        if not attachments:
            missing.append("未上传任何附件")
        # 步骤 2.2：必需附件——必需分类清单由规则参数给出（PRD 未规定各单据类型的必需组合）
        required = [to_text(c) for c in (params.get(KEY_REQUIRED_CATEGORIES) or []) if to_text(c)]
        if required:
            present = {to_text(r.document_category) for r in parse_results}
            missing += ["缺少「%s」类附件" % name for name in required if name not in present]
        # 步骤 2.3：解析置信度——低于阈值即记为低置信度字段（阈值默认取 PRD 5.4 的 0.8）
        threshold = as_decimal(params.get(KEY_LOW_CONFIDENCE)) or DEFAULT_LOW_CONFIDENCE
        for result in parse_results:
            if result.confidence is not None and result.confidence < threshold:
                low_confidence.append({"attachment_id": result.attachment_id,
                                       "document_category": result.document_category,
                                       "confidence": str(result.confidence)})
        # 步骤 2.4：主体一致性——发票销售方与单据供应商名称做精确比对（语义比对属 A3 的 L8）
        mismatches = self._subject_mismatch(document, parse_results)
        # 步骤 3：三项均无问题则未命中
        if not missing and not low_confidence and not mismatches:
            return []
        # 步骤 4：组装结果——缺失项与低置信度字段（PRD 9.1 R09 的输出）
        return [build_result(rule, "附件完整性存在问题",
                             actual={"missing": missing, "low_confidence": low_confidence,
                                     "subject_mismatches": mismatches},
                             reference={"required_categories": required,
                                        "low_confidence_threshold": str(threshold)},
                             evidence={"document_id": document.id,
                                       "attachment_ids": [a.id for a in attachments]})]

    def check_duplicate_invoice(self, document: FinancialDocument, invoices: list[InvoiceRecord],
                                invoice_history: list[InvoiceRecord]) -> list[dict]:
        """R10：与历史发票记录比对，识别重复提交的票据（PRD 9.1 R10）。"""
        # 步骤 1：取规则配置；未配置或无本单发票则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R10_DUPLICATE_INVOICE)
        if rule is None or not invoices:
            return []
        # 步骤 2：建立历史发票的匹配键索引——优先用「发票代码 + 发票号码」，
        #         缺码时退回「销售方 + 含税金额 + 开票日期」（PRD 9.1 R10 的输入维度）
        history_keys: dict[tuple, list[int]] = {}
        for record in invoice_history:
            key = self._invoice_key(record)
            if key is not None:
                history_keys.setdefault(key, []).append(record.id)
        # 步骤 3：逐张本单发票比对；命中即记下重复票据与关联的历史发票主键
        duplicates: list[dict] = []
        for record in invoices:
            key = self._invoice_key(record)
            if key is None:
                continue
            related = history_keys.get(key)
            if related:
                duplicates.append({"invoice_code": record.invoice_code,
                                   "invoice_no": record.invoice_no,
                                   "seller_name": record.seller_name,
                                   "amount_including_tax": None
                                   if record.amount_including_tax is None
                                   else str(record.amount_including_tax),
                                   "related_invoice_ids": related})
        # 步骤 4：无重复则未命中
        if not duplicates:
            return []
        # 步骤 5：组装结果——重复票据与关联单据（PRD 9.1 R10 的输出）
        return [build_result(rule, "存在 %d 张重复票据" % len(duplicates),
                             actual={"duplicates": duplicates},
                             reference={"invoice_history_size": len(invoice_history)},
                             evidence={"document_id": document.id,
                                       "invoice_ids": [i.id for i in invoices]})]

    @staticmethod
    def _unknown_accounts(document: FinancialDocument, line_items: list[DocumentLineItem],
                          supplier: SupplierProfile) -> list[str]:
        """找出不在供应商已知账号集合内的收款账号（PRD 9.1 R08 的「收款账号变更」）。"""
        # 步骤 1：取已知账号集合——bank_accounts_json 视为「账号 → 元数据」的映射，取键为账号；
        #         若某键的值是清单，则其元素也并入（表结构未定义其形态，故同时兼容两种写法）
        known: set[str] = set()
        for key, value in (supplier.bank_accounts_json or {}).items():
            known.add(to_text(key))
            if isinstance(value, (list, tuple, set)):
                known.update(to_text(v) for v in value)
        # 步骤 2：收集本单出现的收款账号（单据级 + 明细级）
        used = {to_text(document.payee_account)} if document.payee_account else set()
        used.update(to_text(i.payee_account) for i in line_items if i.payee_account)
        # 步骤 3：无已知账号可比对时不判定（避免全量误报）
        if not known:
            return []
        # 步骤 4：返回不在已知集合内的账号
        return sorted(account for account in used if account not in known)

    @staticmethod
    def _subject_mismatch(document: FinancialDocument,
                          parse_results: list[AttachmentParseResult]) -> list[dict]:
        """比对发票销售方与单据供应商名称，返回不一致项（精确比对）。"""
        # 步骤 1：取发票附件的销售方字段——A2 的抽取键名 PRD 未列举，故给出候选键
        sellers = set()
        for result in parse_results:
            if to_text(result.document_category) != INVOICE_CATEGORY:
                continue
            fields = result.fields_json or {}
            for key in ("seller_name", "payee_name", "销售方"):
                if fields.get(key):
                    sellers.add(to_text(fields[key]))
        # 步骤 2：单据侧供应商名称缺失或未抽到销售方时不做比对
        if not sellers or not document.supplier_name:
            return []
        # 步骤 3：销售方与单据供应商名称全部不一致即记为不一致项
        target = to_text(document.supplier_name)
        if target in sellers:
            return []
        return [{"document": target, "invoice_sellers": sorted(sellers)}]

    @staticmethod
    def _invoice_key(record: InvoiceRecord) -> tuple | None:
        """生成发票匹配键：优先「发票代码 + 发票号码」，缺码时退回「销售方 + 金额 + 日期」。"""
        # 步骤 1：代码与号码齐备时以二者为键——最可靠的重复判据（PRD 9.1 R10 的输入维度）
        if record.invoice_code and record.invoice_no:
            return ("code_no", to_text(record.invoice_code), to_text(record.invoice_no))
        # 步骤 2：缺码时退回三者组合，避免无键可比导致漏判
        if record.seller_name and record.amount_including_tax is not None:
            return ("seller_amount_date", to_text(record.seller_name),
                    str(record.amount_including_tax),
                    None if record.invoice_date is None else record.invoice_date.isoformat())
        # 步骤 3：连销售方与金额都没有则不生成键，该张跳过
        return None
