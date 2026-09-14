-- 财务单据智能风险审核系统 · 数据库初始化脚本（建库 + 建表 + 索引）
-- 字段依据 PRD 12.1（与 schema/ 逐字段一致）；约束依据 PRD 12.2。
-- 方言 MySQL 8：金额 DECIMAL(18,2)、时间 DATETIME（应用层统一存 UTC）、*_json 用 JSON 列。
-- 可空性 PRD 未定义，故仅主键必填、其余列均可空（与 schema/ 约定一致）。
-- MySQL 对 TEXT 列建索引须给前缀长度，故文本列索引取前 64 字符。

CREATE DATABASE IF NOT EXISTS financial_audit DEFAULT CHARACTER SET utf8mb4;
USE financial_audit;

-- 身份与权限
CREATE TABLE users (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, username TEXT, display_name TEXT,
    password_hash TEXT, status TEXT, created_at DATETIME, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE roles (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, role_code TEXT, role_name TEXT, status TEXT,
    created_at DATETIME, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE permissions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, permission_code TEXT, permission_name TEXT,
    resource_type TEXT, action_type TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE user_roles (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id BIGINT, role_id BIGINT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE role_permissions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, role_id BIGINT, permission_id BIGINT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 审核会话
CREATE TABLE review_sessions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id BIGINT,
    document_type TEXT CHECK (document_type IN ('对公付款单', '预付款单', '批量付款单',
        '费用报销单', '差旅报销单')),
    document_no TEXT, session_status TEXT, created_at DATETIME, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE session_messages (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, session_id BIGINT, role TEXT, content TEXT,
    message_type TEXT, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE session_slots (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, session_id BIGINT, slot_name TEXT,
    slot_value TEXT, is_confirmed BOOLEAN, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 单据与明细
CREATE TABLE financial_documents (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    document_type TEXT CHECK (document_type IN ('对公付款单', '预付款单', '批量付款单',
        '费用报销单', '差旅报销单')),
    document_no TEXT, applicant_id BIGINT, applicant_department TEXT, budget_department TEXT,
    payee_name TEXT, payee_account TEXT, expense_category TEXT, amount DECIMAL(18,2),
    total_amount DECIMAL(18,2), currency TEXT, apply_date DATE, reason_text TEXT, contract_no TEXT,
    supplier_name TEXT, payment_ratio DECIMAL(18,2), payment_terms TEXT, planned_payment_date DATE,
    batch_total_amount DECIMAL(18,2), payment_count BIGINT, travel_destination TEXT,
    travel_start_date DATE, travel_end_date DATE, transport_fee DECIMAL(18,2),
    accommodation_fee DECIMAL(18,2), meal_fee DECIMAL(18,2), allowance DECIMAL(18,2),
    document_status TEXT CHECK (document_status IN ('draft', 'pending_review', 'reviewing',
        'returned', 'approved', 'rejected', 'withdrawn', 'voided')),
    current_version BIGINT, created_at DATETIME, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE document_versions (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, document_id BIGINT, version_no BIGINT,
    document_snapshot_json JSON, created_by BIGINT, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE document_line_items (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, document_id BIGINT, item_type TEXT,
    item_name TEXT, expense_date DATE, expense_location TEXT, expense_account TEXT,
    quantity DECIMAL(18,2), unit_price DECIMAL(18,2), amount DECIMAL(18,2), payee_name TEXT,
    payee_account TEXT, payee_bank TEXT, planned_payment_date DATE, remark TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE document_attachments (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, document_id BIGINT, document_version BIGINT,
    file_name TEXT, file_type TEXT, file_size BIGINT, file_path TEXT, file_hash TEXT,
    storage_status TEXT CHECK (storage_status IN ('uploading', 'stored', 'failed')),
    parse_status TEXT CHECK (parse_status IN ('pending', 'parsing', 'succeeded', 'failed',
        'manual_review')),
    created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE attachment_parse_results (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, attachment_id BIGINT, document_category TEXT,
    full_text TEXT, fields_json JSON, evidence_positions_json JSON, confidence DOUBLE,
    created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE invoice_records (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, attachment_id BIGINT, invoice_code TEXT,
    invoice_no TEXT, seller_name TEXT, buyer_name TEXT, invoice_date DATE,
    amount_excluding_tax DECIMAL(18,2), tax_amount DECIMAL(18,2), amount_including_tax DECIMAL(18,2),
    currency TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 审批
CREATE TABLE approval_workflows (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, workflow_name TEXT,
    document_type TEXT CHECK (document_type IN ('对公付款单', '预付款单', '批量付款单',
        '费用报销单', '差旅报销单')),
    match_conditions_json JSON, status TEXT, created_at DATETIME, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE approval_workflow_nodes (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, workflow_id BIGINT, node_name TEXT,
    node_order BIGINT, approver_role TEXT, approval_mode TEXT, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE approval_instances (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, workflow_id BIGINT, document_id BIGINT,
    document_version BIGINT,
    instance_status TEXT CHECK (instance_status IN ('pending', 'running', 'approved', 'returned',
        'rejected', 'cancelled')),
    current_node_id BIGINT, started_at DATETIME, finished_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE approval_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, instance_id BIGINT, node_id BIGINT,
    approver_id BIGINT,
    task_status TEXT CHECK (task_status IN ('pending', 'approved', 'returned', 'rejected',
        'cancelled')),
    review_comment TEXT, created_at DATETIME, processed_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE document_status_logs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, document_id BIGINT,
    from_status TEXT CHECK (from_status IN ('draft', 'pending_review', 'reviewing', 'returned',
        'approved', 'rejected', 'withdrawn', 'voided')),
    to_status TEXT CHECK (to_status IN ('draft', 'pending_review', 'reviewing', 'returned',
        'approved', 'rejected', 'withdrawn', 'voided')),
    operator_id BIGINT, remark TEXT, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 分析与报告
CREATE TABLE analysis_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, session_id BIGINT, document_id BIGINT,
    task_status TEXT CHECK (task_status IN ('queued', 'querying_document', 'loading_attachments',
        'parsing_attachments', 'analyzing', 'succeeded', 'failed', 'cancelled')),
    current_step TEXT, started_at DATETIME, finished_at DATETIME, error_message TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE risk_findings (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, task_id BIGINT, risk_type TEXT,
    risk_level TEXT CHECK (risk_level IN ('low', 'medium', 'high')), risk_title TEXT,
    description TEXT, actual_value_json JSON, reference_value_json JSON, threshold_json JSON,
    evidence_json JSON, suggestion_text TEXT,
    review_status TEXT CHECK (review_status IN ('pending', 'confirmed', 'dismissed')),
    created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE review_reports (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, task_id BIGINT, document_id BIGINT,
    overall_risk_level TEXT CHECK (overall_risk_level IN ('low', 'medium', 'high')),
    risk_summary_json JSON, amount_comparison_json JSON,
    recommendation TEXT CHECK (recommendation IN ('建议通过', '补充材料', '人工复核', '建议驳回')),
    report_markdown TEXT, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE manual_reviews (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, report_id BIGINT, reviewer_id BIGINT,
    review_result TEXT, review_comment TEXT, reviewed_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 规则与费用标准
CREATE TABLE review_rules (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, rule_code TEXT, rule_name TEXT, rule_type TEXT,
    params_json JSON, status TEXT, effective_date DATE, updated_by BIGINT, updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE expense_standards (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, expense_category TEXT, department TEXT,
    job_level TEXT, region TEXT, standard_amount DECIMAL(18,2), currency TEXT, effective_date DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- 参考数据与审计
CREATE TABLE market_price_references (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, item_name TEXT, specification TEXT, region TEXT,
    price_min DECIMAL(18,2), price_max DECIMAL(18,2), currency TEXT, source_name TEXT,
    effective_date DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE supplier_profiles (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, supplier_code TEXT, supplier_name TEXT,
    credit_status TEXT, blacklist_status TEXT, risk_tags_json JSON, bank_accounts_json JSON,
    updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE audit_logs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id BIGINT, action_type TEXT,
    resource_type TEXT, resource_id BIGINT, detail_json JSON, created_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 索引与唯一约束（PRD 12.2）
CREATE UNIQUE INDEX ux_financial_documents_document_no
    ON financial_documents (document_no(64));  -- 单据编号全局唯一
CREATE INDEX ix_review_sessions_user_status ON review_sessions (user_id, session_status(64));
CREATE INDEX ix_financial_documents_type_status
    ON financial_documents (document_type(64), document_status(64));
CREATE INDEX ix_financial_documents_applicant ON financial_documents (applicant_id);
CREATE INDEX ix_financial_documents_apply_date ON financial_documents (apply_date);
CREATE INDEX ix_approval_tasks_approver_status ON approval_tasks (approver_id, task_status(64));
CREATE INDEX ix_risk_findings_task_level ON risk_findings (task_id, risk_level(64));
