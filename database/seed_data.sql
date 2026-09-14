-- 财务单据智能风险审核系统 · 示例数据（PRD 19.1）
-- 覆盖：四类角色用户、五类单据（高/中/无风险）、费用与付款明细、五类附件（PDF/PNG/JPG）、
--       附件解析结果（含页码与证据位置）、发票记录（含 1 张跨单据重复票据）、
--       黑名单供应商与收款账号变更供应商、市场价参考、R01~R10 规则集与三段审批流程。
-- 账号：applicant1 / approver1 / finance1 / admin1，初始密码均为 123456（加盐哈希存储）。
-- 显式指定主键以便核对；重复执行前需先清空相关表或重建数据库。

USE financial_audit;

INSERT INTO users (id, username, display_name, password_hash, status, created_at, updated_at) VALUES
    (1, 'applicant1', '张申请', 'pbkdf2_sha256$120000$e2458fda364e4d88ddfe13996b0d7bd8$z9MJh9FmWCMq1HEX94FkmIhI6zdqzPLvCaN7AOE1TBo=', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (2, 'approver1', '李审批', 'pbkdf2_sha256$120000$e2458fda364e4d88ddfe13996b0d7bd8$z9MJh9FmWCMq1HEX94FkmIhI6zdqzPLvCaN7AOE1TBo=', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (3, 'finance1', '王财务', 'pbkdf2_sha256$120000$e2458fda364e4d88ddfe13996b0d7bd8$z9MJh9FmWCMq1HEX94FkmIhI6zdqzPLvCaN7AOE1TBo=', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (4, 'admin1', '赵管理', 'pbkdf2_sha256$120000$e2458fda364e4d88ddfe13996b0d7bd8$z9MJh9FmWCMq1HEX94FkmIhI6zdqzPLvCaN7AOE1TBo=', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00');
INSERT INTO roles (id, role_code, role_name, status, created_at, updated_at) VALUES
    (1, 'applicant', '单据申请人', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (2, 'approver', '审批人员', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (3, 'finance', '财务人员', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (4, 'admin', '系统管理员', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00');
INSERT INTO permissions (id, permission_code, permission_name, resource_type, action_type) VALUES
    (1, 'document.create', '创建与编辑本人单据', 'financial_documents', 'write'),
    (2, 'document.view_self', '查看本人单据', 'financial_documents', 'read'),
    (3, 'document.view_all', '查看全部单据', 'financial_documents', 'read'),
    (4, 'document.submit', '提交、撤回与作废单据', 'financial_documents', 'write'),
    (5, 'attachment.write', '上传与删除附件', 'document_attachments', 'write'),
    (6, 'analysis.start', '发起风险分析', 'analysis_tasks', 'write'),
    (7, 'analysis.view', '查看风险面板与证据', 'risk_findings', 'read'),
    (8, 'review.submit', '填写复核意见与审批结果', 'manual_reviews', 'write'),
    (9, 'rule.manage', '维护审核规则与参考数据', 'review_rules', 'write'),
    (10, 'system.manage', '维护用户、角色、权限与流程', 'approval_workflows', 'write');
INSERT INTO user_roles (id, user_id, role_id) VALUES
    (1, 1, 1),
    (2, 2, 2),
    (3, 3, 3),
    (4, 4, 4);
INSERT INTO role_permissions (id, role_id, permission_id) VALUES
    (1, 1, 1),
    (2, 1, 2),
    (3, 1, 4),
    (4, 1, 5),
    (5, 2, 2),
    (6, 2, 3),
    (7, 2, 6),
    (8, 2, 7),
    (9, 2, 8),
    (10, 3, 2),
    (11, 3, 3),
    (12, 3, 6),
    (13, 3, 7),
    (14, 3, 9),
    (15, 4, 2),
    (16, 4, 3),
    (17, 4, 6),
    (18, 4, 7),
    (19, 4, 9),
    (20, 4, 10);
INSERT INTO approval_workflows (id, workflow_name, document_type, match_conditions_json, status, created_at, updated_at) VALUES
    (1, '对公付款单标准流程', '对公付款单', '{"min_amount": 0, "max_amount": 1000000}', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (2, '对公付款单大额流程', '对公付款单', '{"min_amount": 1000000}', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00'),
    (3, '费用报销单标准流程', '费用报销单', '{"min_amount": 0}', 'active', '2026-09-14 08:00:00', '2026-09-14 08:00:00');
INSERT INTO approval_workflow_nodes (id, workflow_id, node_name, node_order, approver_role, approval_mode, created_at) VALUES
    (1, 1, '部门负责人审批', 1, 'approver', 'single', '2026-09-14 08:00:00'),
    (2, 1, '财务复核', 2, 'approver', 'single', '2026-09-14 08:00:00'),
    (3, 1, '分管领导审批', 3, 'approver', 'single', '2026-09-14 08:00:00'),
    (4, 2, '部门负责人审批', 1, 'approver', 'single', '2026-09-14 08:00:00'),
    (5, 2, '财务复核', 2, 'approver', 'single', '2026-09-14 08:00:00'),
    (6, 2, '分管领导审批', 3, 'approver', 'single', '2026-09-14 08:00:00'),
    (7, 3, '部门负责人审批', 1, 'approver', 'single', '2026-09-14 08:00:00'),
    (8, 3, '财务复核', 2, 'approver', 'single', '2026-09-14 08:00:00');
INSERT INTO review_rules (id, rule_code, rule_name, rule_type, params_json, status, effective_date, updated_by, updated_at) VALUES
    (1, 'R01', '单据与发票金额一致性', 'amount', '{"tolerance": "0.01", "medium_ratio": "0.05", "high_ratio": "0.20"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (2, 'R02', '明细与总金额一致性', 'amount', '{"tolerance": "0.01", "medium_ratio": "0.03", "high_ratio": "0.10"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (3, 'R03', '合同与付款一致性', 'amount', '{"tolerance": "0.01", "medium_ratio": "0.05", "high_ratio": "0.15"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (4, 'R04', '批量付款一致性', 'amount', '{"tolerance": "0.01", "level": "high"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (5, 'R05', '费用标准合规性', 'expense', '{"level": "medium"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (6, 'R06', '市场价格合理性', 'expense', '{"medium_ratio": "0.20", "high_ratio": "0.50"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (7, 'R07', '消费行为异常', 'behavior', '{"window_days": "7", "min_count": "3", "split_max_amount": "1000", "surge_ratio": "3", "medium_ratio": "0.5", "high_ratio": "2"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (8, 'R08', '供应商风险', 'supplier', '{"blacklist_values": ["blacklisted"], "credit_abnormal_values": ["abnormal"], "level": "high"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (9, 'R09', '附件完整性', 'attachment', '{"required_categories": ["发票", "合同"], "level": "medium"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00'),
    (10, 'R10', '重复票据风险', 'duplicate_invoice', '{"level": "high"}', 'active', '2026-01-01', 4, '2026-09-14 08:00:00');
INSERT INTO expense_standards (id, expense_category, department, region, standard_amount, currency, effective_date) VALUES
    (1, '住宿费', '技术部', '深圳', 500.00, 'CNY', '2026-01-01'),
    (2, '住宿费', '技术部', '北京', 600.00, 'CNY', '2026-01-01'),
    (3, '餐费', '技术部', '深圳', 150.00, 'CNY', '2026-01-01');
INSERT INTO market_price_references (id, item_name, specification, region, price_min, price_max, currency, source_name, effective_date) VALUES
    (1, '笔记本电脑', 'i7/16G/512G', '深圳', 4000.00, 6000.00, 'CNY', '电商平台均值', '2026-06-01'),
    (2, '办公桌', '1.4m', '深圳', 600.00, 1200.00, 'CNY', '电商平台均值', '2026-06-01');
INSERT INTO supplier_profiles (id, supplier_code, supplier_name, credit_status, blacklist_status, risk_tags_json, bank_accounts_json, updated_at) VALUES
    (1, 'SUP001', '某某建设集团有限公司', 'normal', 'normal', '{"tags": []}', '{"6222020200112233445": "建设银行深圳分行"}', '2026-09-14 08:00:00'),
    (2, 'SUP002', '恒昌物资贸易有限公司', 'normal', 'blacklisted', '{"tags": ["黑名单"]}', '{"6222020200998877665": "工商银行深圳分行"}', '2026-09-14 08:00:00'),
    (3, 'SUP003', '远景科技有限公司', 'normal', 'normal', '{"tags": ["收款账号变更"]}', '{"6222020200111100000": "建设银行深圳分行", "6222020200111100001": "招商银行深圳分行（历史）"}', '2026-09-14 08:00:00');
INSERT INTO financial_documents (id, document_type, document_no, applicant_id, applicant_department, budget_department, payee_name, payee_account, expense_category, amount, total_amount, currency, apply_date, reason_text, contract_no, supplier_name, payment_ratio, payment_terms, planned_payment_date, document_status, current_version, created_at, updated_at, batch_total_amount, payment_count, travel_destination, travel_start_date, travel_end_date, transport_fee, accommodation_fee, meal_fee, allowance) VALUES
    (1, '对公付款单', 'FKD-2026-0001', 1, '技术部', '技术部', '恒昌物资贸易有限公司', '6222020200998877665', '设备采购', 500000.00, 500000.00, 'CNY', '2026-09-01', '机房服务器与网络设备采购款', 'HT-2026-0801', '恒昌物资贸易有限公司', 0.50, '验收合格后 30 日内支付', '2026-09-30', 'pending_review', 1, '2026-09-14 08:00:00', '2026-09-14 08:00:00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (2, '预付款单', 'YFK-2026-0001', 1, '工程部', '工程部', '某某建设集团有限公司', '6222020200112233445', '工程预付款', 500000.00, 500000.00, 'CNY', '2026-08-20', '厂房改造工程预付款', 'HT-2026-0715', '某某建设集团有限公司', 0.20, '按工程进度分三期支付', '2026-09-10', 'pending_review', 1, '2026-09-14 08:00:00', '2026-09-14 08:00:00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (3, '批量付款单', 'PLFK-2026-0001', 1, '财务部', '财务部', '批量代发', '6222020200000000001', '供应商货款', 100000.00, 100000.00, 'CNY', '2026-09-05', '季度供应商货款批量支付', NULL, NULL, NULL, NULL, NULL, 'approved', 1, '2026-09-14 08:00:00', '2026-09-14 08:00:00', 100000.00, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (4, '费用报销单', 'FYBX-2026-0001', 1, '技术部', '技术部', '张申请', '6222020200334455667', '办公设备', 9000.00, 9000.00, 'CNY', '2026-09-08', '研发工位设备采购报销', NULL, NULL, NULL, NULL, NULL, 'pending_review', 1, '2026-09-14 08:00:00', '2026-09-14 08:00:00', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (5, '差旅报销单', 'CLBX-2026-0001', 1, '技术部', '技术部', '张申请', '6222020200334455667', '差旅费', 2950.00, 2950.00, 'CNY', '2026-08-08', '深圳客户现场支持差旅', NULL, NULL, NULL, NULL, NULL, 'pending_review', 1, '2026-09-14 08:00:00', '2026-09-14 08:00:00', NULL, NULL, '深圳', '2026-08-03', '2026-08-05', 1200.00, 1000.00, 450.00, 300.00);
INSERT INTO document_line_items (id, document_id, item_type, item_name, amount, payee_name, payee_account, payee_bank, planned_payment_date, remark, expense_date, expense_location, expense_account, quantity, unit_price) VALUES
    (1, 1, '付款明细', '服务器采购款', 250000.00, '恒昌物资贸易有限公司', '6222020200998877665', '工商银行深圳分行', '2026-09-30', '第一批设备款', NULL, NULL, NULL, NULL, NULL),
    (2, 1, '付款明细', '网络设备采购款', 250000.00, '恒昌物资贸易有限公司', '6222020200998877665', '工商银行深圳分行', '2026-09-30', '第二批设备款', NULL, NULL, NULL, NULL, NULL),
    (3, 3, '付款明细', '甲供应商货款', 60000.00, '远景科技有限公司', '6222020200111100000', '建设银行深圳分行', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (4, 3, '付款明细', '乙供应商货款', 40000.00, '某某建设集团有限公司', '6222020200112233445', '建设银行深圳分行', NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    (5, 4, '费用明细', '笔记本电脑', 8000.00, NULL, NULL, NULL, NULL, 'i7/16G/512G', '2026-09-02', '深圳', '研发费用', 1.00, 8000.00),
    (6, 4, '费用明细', '办公桌', 1000.00, NULL, NULL, NULL, NULL, '1.4m', '2026-09-02', '深圳', '研发费用', 1.00, 1000.00),
    (7, 5, '费用明细', '往返交通费', 1200.00, NULL, NULL, NULL, NULL, NULL, '2026-08-03', '深圳', '差旅费', NULL, NULL),
    (8, 5, '费用明细', '住宿费', 1000.00, NULL, NULL, NULL, NULL, NULL, '2026-08-04', '深圳', '差旅费', NULL, NULL),
    (9, 5, '费用明细', '餐费', 450.00, NULL, NULL, NULL, NULL, NULL, '2026-08-05', '深圳', '差旅费', NULL, NULL);
INSERT INTO document_attachments (id, document_id, document_version, storage_status, parse_status, created_at, file_name, file_type, file_size, file_path, file_hash) VALUES
    (1, 1, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '增值税专用发票.pdf', 'PDF', 780, '1/5702e2b1ef94432a828ced24112be75cf9334573a4b66cdb1438c4ca489c769b.pdf', '5702e2b1ef94432a828ced24112be75cf9334573a4b66cdb1438c4ca489c769b'),
    (2, 1, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '设备采购合同.pdf', 'PDF', 743, '1/78e18887f0fe5c3d9c25df826f12431514f059d986436c70b787a2a52c06b87a.pdf', '78e18887f0fe5c3d9c25df826f12431514f059d986436c70b787a2a52c06b87a'),
    (3, 1, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '付款申请单.png', 'PNG', 9075, '1/b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee.png', 'b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee'),
    (4, 2, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '工程合同.pdf', 'PDF', 743, '2/78e18887f0fe5c3d9c25df826f12431514f059d986436c70b787a2a52c06b87a.pdf', '78e18887f0fe5c3d9c25df826f12431514f059d986436c70b787a2a52c06b87a'),
    (5, 2, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '预付款申请单.png', 'PNG', 9075, '2/b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee.png', 'b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee'),
    (6, 3, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '批量付款清单.png', 'PNG', 9075, '3/b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee.png', 'b1d41976353aca666ef5b5037973be1a3183fa2db6c7eb3e5e3a573e7a4207ee'),
    (7, 4, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '设备发票.jpg', 'JPG', 13998, '4/7b867bfd7f6c788714d1b6ccaecbe172ca7a1a0896eebb7154384639aedf6680.jpg', '7b867bfd7f6c788714d1b6ccaecbe172ca7a1a0896eebb7154384639aedf6680'),
    (8, 4, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '费用清单.jpg', 'JPG', 10510, '4/edf6e228fa8740c28fdd2ad8eaa2a57e01a60d5cae113672853b0d6b2c199a18.jpg', 'edf6e228fa8740c28fdd2ad8eaa2a57e01a60d5cae113672853b0d6b2c199a18'),
    (9, 5, 1, 'stored', 'succeeded', '2026-09-14 08:00:00', '差旅行程单.png', 'PNG', 7819, '5/f4a7bd4b223c589443c3a323ebfbf56987a6a9889ad38fc58b75f64e98bd4477.png', 'f4a7bd4b223c589443c3a323ebfbf56987a6a9889ad38fc58b75f64e98bd4477');
INSERT INTO attachment_parse_results (id, attachment_id, document_category, full_text, fields_json, evidence_positions_json, confidence, created_at) VALUES
    (1, 1, '发票', 'invoice_code: 044001900111
invoice_no: 12345678
seller_name: 恒昌物资贸易有限公司
invoice_date: 2026-08-28
amount_including_tax: 300000.00
currency: CNY', '{"invoice_code": "044001900111", "invoice_no": "12345678", "seller_name": "恒昌物资贸易有限公司", "invoice_date": "2026-08-28", "amount_including_tax": "300000.00", "currency": "CNY"}', '[{"field_name": "invoice_code", "page_no": 1, "confidence": 0.92, "evidence_text": "044001900111", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "invoice_no", "page_no": 1, "confidence": 0.92, "evidence_text": "12345678", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "seller_name", "page_no": 1, "confidence": 0.92, "evidence_text": "恒昌物资贸易有限公司", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}, {"field_name": "invoice_date", "page_no": 1, "confidence": 0.92, "evidence_text": "2026-08-28", "bbox": {"x0": 0.08, "y0": 0.25, "x1": 0.62, "y1": 0.28}}, {"field_name": "amount_including_tax", "page_no": 1, "confidence": 0.92, "evidence_text": "300000.00", "bbox": {"x0": 0.08, "y0": 0.30000000000000004, "x1": 0.62, "y1": 0.33000000000000007}}, {"field_name": "currency", "page_no": 1, "confidence": 0.92, "evidence_text": "CNY", "bbox": {"x0": 0.08, "y0": 0.35, "x1": 0.62, "y1": 0.38}}]', '0.94', '2026-09-14 08:00:00'),
    (2, 2, '合同', 'contract_no: HT-2026-0801
supplier_name: 恒昌物资贸易有限公司
contract_amount: 1000000.00
payment_ratio: 0.30', '{"contract_no": "HT-2026-0801", "supplier_name": "恒昌物资贸易有限公司", "contract_amount": "1000000.00", "payment_ratio": "0.30"}', '[{"field_name": "contract_no", "page_no": 1, "confidence": 0.89, "evidence_text": "HT-2026-0801", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "supplier_name", "page_no": 1, "confidence": 0.89, "evidence_text": "恒昌物资贸易有限公司", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "contract_amount", "page_no": 1, "confidence": 0.89, "evidence_text": "1000000.00", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}, {"field_name": "payment_ratio", "page_no": 1, "confidence": 0.89, "evidence_text": "0.30", "bbox": {"x0": 0.08, "y0": 0.25, "x1": 0.62, "y1": 0.28}}]', '0.91', '2026-09-14 08:00:00'),
    (3, 3, '付款依据', 'voucher_no: FK-2026-0001
payee_name: 恒昌物资贸易有限公司
total_amount: 500000.00', '{"voucher_no": "FK-2026-0001", "payee_name": "恒昌物资贸易有限公司", "total_amount": "500000.00"}', '[{"field_name": "voucher_no", "page_no": 1, "confidence": 0.86, "evidence_text": "FK-2026-0001", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "payee_name", "page_no": 1, "confidence": 0.86, "evidence_text": "恒昌物资贸易有限公司", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "total_amount", "page_no": 1, "confidence": 0.86, "evidence_text": "500000.00", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}]', '0.88', '2026-09-14 08:00:00'),
    (4, 4, '合同', 'contract_no: HT-2026-0715
supplier_name: 某某建设集团有限公司
contract_amount: 2500000.00
payment_ratio: 0.30', '{"contract_no": "HT-2026-0715", "supplier_name": "某某建设集团有限公司", "contract_amount": "2500000.00", "payment_ratio": "0.30"}', '[{"field_name": "contract_no", "page_no": 1, "confidence": 0.88, "evidence_text": "HT-2026-0715", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "supplier_name", "page_no": 1, "confidence": 0.88, "evidence_text": "某某建设集团有限公司", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "contract_amount", "page_no": 1, "confidence": 0.88, "evidence_text": "2500000.00", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}, {"field_name": "payment_ratio", "page_no": 1, "confidence": 0.88, "evidence_text": "0.30", "bbox": {"x0": 0.08, "y0": 0.25, "x1": 0.62, "y1": 0.28}}]', '0.9', '2026-09-14 08:00:00'),
    (5, 5, '付款依据', 'voucher_no: YFK-2026-0001
payee_name: 某某建设集团有限公司
total_amount: 500000.00', '{"voucher_no": "YFK-2026-0001", "payee_name": "某某建设集团有限公司", "total_amount": "500000.00"}', '[{"field_name": "voucher_no", "page_no": 1, "confidence": 0.85, "evidence_text": "YFK-2026-0001", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "payee_name", "page_no": 1, "confidence": 0.85, "evidence_text": "某某建设集团有限公司", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "total_amount", "page_no": 1, "confidence": 0.85, "evidence_text": "500000.00", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}]', '0.87', '2026-09-14 08:00:00'),
    (6, 6, '付款依据', 'voucher_no: PLFK-2026-0001
total_amount: 100000.00', '{"voucher_no": "PLFK-2026-0001", "total_amount": "100000.00"}', '[{"field_name": "voucher_no", "page_no": 1, "confidence": 0.87, "evidence_text": "PLFK-2026-0001", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "total_amount", "page_no": 1, "confidence": 0.87, "evidence_text": "100000.00", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}]', '0.89', '2026-09-14 08:00:00'),
    (7, 7, '发票', 'invoice_code: 044001900111
invoice_no: 12345678
seller_name: 恒昌物资贸易有限公司
invoice_date: 2026-08-28
amount_including_tax: 300000.00
currency: CNY', '{"invoice_code": "044001900111", "invoice_no": "12345678", "seller_name": "恒昌物资贸易有限公司", "invoice_date": "2026-08-28", "amount_including_tax": "300000.00", "currency": "CNY"}', '[{"field_name": "invoice_code", "page_no": 1, "confidence": 0.9, "evidence_text": "044001900111", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "invoice_no", "page_no": 1, "confidence": 0.9, "evidence_text": "12345678", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "seller_name", "page_no": 1, "confidence": 0.9, "evidence_text": "恒昌物资贸易有限公司", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}, {"field_name": "invoice_date", "page_no": 1, "confidence": 0.9, "evidence_text": "2026-08-28", "bbox": {"x0": 0.08, "y0": 0.25, "x1": 0.62, "y1": 0.28}}, {"field_name": "amount_including_tax", "page_no": 1, "confidence": 0.9, "evidence_text": "300000.00", "bbox": {"x0": 0.08, "y0": 0.30000000000000004, "x1": 0.62, "y1": 0.33000000000000007}}, {"field_name": "currency", "page_no": 1, "confidence": 0.9, "evidence_text": "CNY", "bbox": {"x0": 0.08, "y0": 0.35, "x1": 0.62, "y1": 0.38}}]', '0.92', '2026-09-14 08:00:00'),
    (8, 8, '费用明细', 'item_total: 9000.00', '{"item_total": "9000.00"}', '[{"field_name": "item_total", "page_no": 1, "confidence": 0.88, "evidence_text": "9000.00", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}]', '0.9', '2026-09-14 08:00:00'),
    (9, 9, '行程单', 'traveler: 张申请
travel_destination: 深圳
travel_start_date: 2026-08-03
travel_end_date: 2026-08-05', '{"traveler": "张申请", "travel_destination": "深圳", "travel_start_date": "2026-08-03", "travel_end_date": "2026-08-05"}', '[{"field_name": "traveler", "page_no": 1, "confidence": 0.84, "evidence_text": "张申请", "bbox": {"x0": 0.08, "y0": 0.1, "x1": 0.62, "y1": 0.13}}, {"field_name": "travel_destination", "page_no": 1, "confidence": 0.84, "evidence_text": "深圳", "bbox": {"x0": 0.08, "y0": 0.15000000000000002, "x1": 0.62, "y1": 0.18000000000000002}}, {"field_name": "travel_start_date", "page_no": 1, "confidence": 0.84, "evidence_text": "2026-08-03", "bbox": {"x0": 0.08, "y0": 0.2, "x1": 0.62, "y1": 0.23}}, {"field_name": "travel_end_date", "page_no": 1, "confidence": 0.84, "evidence_text": "2026-08-05", "bbox": {"x0": 0.08, "y0": 0.25, "x1": 0.62, "y1": 0.28}}]', '0.86', '2026-09-14 08:00:00');
INSERT INTO invoice_records (id, attachment_id, invoice_code, invoice_no, seller_name, buyer_name, invoice_date, amount_excluding_tax, tax_amount, amount_including_tax, currency) VALUES
    (1, 1, '044001900111', '12345678', '恒昌物资贸易有限公司', '本单位', '2026-08-28', 283018.87, 16981.13, 300000.00, 'CNY'),
    (2, 7, '044001900111', '12345678', '恒昌物资贸易有限公司', '本单位', '2026-08-28', 283018.87, 16981.13, 300000.00, 'CNY');
