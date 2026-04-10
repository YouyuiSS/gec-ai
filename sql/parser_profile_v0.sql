-- Draft schema for the web-side parser profile repair workflow.
-- This file adds a versioned parser-profile model without coupling it to local OpenCode skills.

begin;

create table if not exists parser_profile (
    id bigserial primary key,
    jurisdiction text not null,
    tax_domain text not null,
    document_family text not null,
    language_code text not null default 'und',
    status text not null default 'active'
        check (status in ('active', 'disabled')),
    active_version_id bigint,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (jurisdiction, tax_domain, document_family, language_code)
);

create table if not exists parser_profile_version (
    id bigserial primary key,
    parser_profile_id bigint not null references parser_profile(id) on delete cascade,
    version_no integer not null check (version_no > 0),
    schema_version text not null,
    metadata_json jsonb not null,
    source text not null
        check (source in ('human', 'ai')),
    change_summary text,
    created_by text not null,
    created_at timestamptz not null default now(),
    unique (parser_profile_id, version_no),
    check (jsonb_typeof(metadata_json) = 'object')
);

create table if not exists parser_repair_ticket (
    id bigserial primary key,
    extraction_run_id bigint not null references extraction_run(id) on delete cascade,
    parser_profile_version_id bigint not null references parser_profile_version(id) on delete restrict,
    candidate_profile_version_id bigint references parser_profile_version(id) on delete set null,
    field_code text,
    issue_type text not null
        check (issue_type in ('header_alias', 'path_replace_rule', 'block_score', 'constraint_rule')),
    feedback_text text not null,
    expected_value_json jsonb,
    evidence_pages integer[] not null default '{}'::integer[],
    request_payload jsonb,
    model_response jsonb,
    patch_json jsonb,
    rerun_summary jsonb,
    status text not null default 'open'
        check (status in ('open', 'suggested', 'rerun_succeeded', 'rerun_failed', 'applied', 'rejected')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (expected_value_json is null or jsonb_typeof(expected_value_json) = 'object'),
    check (request_payload is null or jsonb_typeof(request_payload) = 'object'),
    check (model_response is null or jsonb_typeof(model_response) in ('object', 'array')),
    check (patch_json is null or jsonb_typeof(patch_json) = 'object'),
    check (rerun_summary is null or jsonb_typeof(rerun_summary) = 'object')
);

create index if not exists idx_parser_profile_lookup
    on parser_profile(jurisdiction, tax_domain, document_family, language_code);

create index if not exists idx_parser_profile_version_profile
    on parser_profile_version(parser_profile_id, version_no desc);

create index if not exists idx_parser_repair_ticket_run
    on parser_repair_ticket(extraction_run_id, created_at desc);

create index if not exists idx_parser_repair_ticket_status
    on parser_repair_ticket(status, created_at desc);

alter table if exists extraction_run
    add column if not exists parser_profile_version_id bigint references parser_profile_version(id) on delete restrict;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'parser_profile_active_version_fk'
    ) then
        alter table parser_profile
            add constraint parser_profile_active_version_fk
            foreign key (active_version_id)
            references parser_profile_version(id)
            on delete set null;
    end if;
end
$$;

commit;
