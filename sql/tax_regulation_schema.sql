-- PostgreSQL starter schema for a tax regulation continuous-update system.

create table if not exists source_document (
    id bigserial primary key,
    jurisdiction text not null,
    tax_domain text not null,
    language_code text,
    source_uri text,
    original_filename text not null,
    checksum_sha256 text not null unique,
    uploaded_at timestamptz not null default now()
);

create table if not exists document_version (
    id bigserial primary key,
    source_document_id bigint not null references source_document(id) on delete cascade,
    version_label text not null,
    issued_on date,
    effective_from date,
    effective_to date,
    status text not null default 'candidate',
    parser_fingerprint text,
    llm_fingerprint text,
    created_at timestamptz not null default now(),
    published_at timestamptz,
    unique (source_document_id, version_label)
);

create table if not exists extraction_run (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    stage text not null,
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    tool_version text,
    llm_model text,
    prompt_version text,
    metrics jsonb not null default '{}'::jsonb
);

create table if not exists citation (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    page_number integer not null check (page_number > 0),
    section_title text,
    source_kind text not null,
    quote_text text not null,
    anchor_text text,
    created_at timestamptz not null default now()
);

create table if not exists field_definition (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    field_code text not null,
    field_kind text not null default 'atomic',
    parent_group_code text,
    field_name text not null,
    field_description text,
    data_type text,
    occurrence_min integer,
    occurrence_max text,
    sample_value text,
    value_set_refs jsonb not null default '[]'::jsonb,
    semantic_notes text,
    report_level text,
    min_char_length integer,
    max_char_length integer,
    min_decimal_scale integer,
    max_decimal_scale integer,
    origin text not null default 'explicit',
    confidence numeric(4,3) not null default 1.000,
    created_at timestamptz not null default now(),
    unique (document_version_id, field_code)
);

create table if not exists field_path (
    id bigserial primary key,
    field_definition_id bigint not null references field_definition(id) on delete cascade,
    doc_kind text not null check (doc_kind in ('invoice', 'credit_note')),
    path_expr text not null,
    remark text,
    unique (field_definition_id, doc_kind)
);

create table if not exists field_citation (
    field_definition_id bigint not null references field_definition(id) on delete cascade,
    citation_id bigint not null references citation(id) on delete cascade,
    primary key (field_definition_id, citation_id)
);

create table if not exists rule_definition (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    rule_code text not null,
    rule_type text not null,
    severity text not null default 'error',
    expression_text text not null,
    normalized_expression jsonb not null default '{}'::jsonb,
    origin text not null default 'explicit',
    confidence numeric(4,3) not null default 1.000,
    created_at timestamptz not null default now(),
    unique (document_version_id, rule_code)
);

create table if not exists rule_field_link (
    rule_definition_id bigint not null references rule_definition(id) on delete cascade,
    field_definition_id bigint not null references field_definition(id) on delete cascade,
    role text,
    primary key (rule_definition_id, field_definition_id)
);

create table if not exists rule_citation (
    rule_definition_id bigint not null references rule_definition(id) on delete cascade,
    citation_id bigint not null references citation(id) on delete cascade,
    primary key (rule_definition_id, citation_id)
);

create table if not exists version_diff (
    id bigserial primary key,
    base_version_id bigint references document_version(id) on delete set null,
    candidate_version_id bigint not null references document_version(id) on delete cascade,
    status text not null default 'pending_review',
    created_at timestamptz not null default now(),
    summary jsonb not null default '{}'::jsonb
);

create table if not exists field_change (
    id bigserial primary key,
    version_diff_id bigint not null references version_diff(id) on delete cascade,
    field_code text not null,
    change_type text not null,
    risk_level text not null,
    before_payload jsonb,
    after_payload jsonb,
    auto_approved boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists review_decision (
    id bigserial primary key,
    version_diff_id bigint not null references version_diff(id) on delete cascade,
    reviewer text not null,
    decision text not null,
    comment text,
    decided_at timestamptz not null default now()
);

create table if not exists publication_bundle (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    bundle_type text not null,
    bundle_status text not null default 'draft',
    artifact_uri text not null,
    checksum_sha256 text not null,
    created_at timestamptz not null default now(),
    unique (document_version_id, bundle_type, bundle_status)
);

create table if not exists code_list_definition (
    id bigserial primary key,
    document_version_id bigint not null references document_version(id) on delete cascade,
    code_list_name text not null,
    origin text not null default 'explicit',
    confidence numeric(4,3) not null default 1.000,
    created_at timestamptz not null default now(),
    unique (document_version_id, code_list_name)
);

create table if not exists code_list_entry (
    id bigserial primary key,
    code_list_definition_id bigint not null references code_list_definition(id) on delete cascade,
    code text not null,
    label text not null,
    description text,
    unique (code_list_definition_id, code)
);

create table if not exists code_list_citation (
    code_list_definition_id bigint not null references code_list_definition(id) on delete cascade,
    citation_id bigint not null references citation(id) on delete cascade,
    primary key (code_list_definition_id, citation_id)
);

create table if not exists review_queue_item (
    id bigserial primary key,
    version_diff_id bigint not null references version_diff(id) on delete cascade,
    item_id text not null,
    risk_level text not null,
    message text not null,
    field_code text,
    change_type text,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    unique (version_diff_id, item_id)
);

create index if not exists idx_document_version_status
    on document_version(status);

create index if not exists idx_field_definition_doc_version
    on field_definition(document_version_id);

create index if not exists idx_rule_definition_doc_version
    on rule_definition(document_version_id);

create index if not exists idx_citation_doc_version_page
    on citation(document_version_id, page_number);
