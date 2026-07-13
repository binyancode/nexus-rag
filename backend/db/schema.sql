/* ============================================================================
   Nexus Retrieval Engine — destructive rebuild schema (SQL Server / Azure SQL)

   This script intentionally drops and recreates all Nexus domain/config/run data.
   It preserves only system tables managed elsewhere:
     nexus.api_log / nexus.app_credential / nexus.app_user

   Design source: doc/数据库表结构设计.md
   No foreign keys: application services and the index quality gate enforce integrity.
   ============================================================================ */

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF SCHEMA_ID('nexus') IS NULL EXEC('CREATE SCHEMA nexus');
GO

/* Remove any old foreign keys before the destructive reset. */
DECLARE @drop_fk nvarchar(max) = N'';
SELECT @drop_fk = @drop_fk
    + N'ALTER TABLE ' + QUOTENAME(SCHEMA_NAME(o.schema_id)) + N'.' + QUOTENAME(o.name)
    + N' DROP CONSTRAINT ' + QUOTENAME(fk.name) + N';' + CHAR(10)
FROM sys.foreign_keys fk
JOIN sys.objects o ON fk.parent_object_id = o.object_id
WHERE SCHEMA_NAME(o.schema_id) = 'nexus';
IF LEN(@drop_fk) > 0 EXEC sp_executesql @drop_fk;
GO

/* Drop new and legacy domain tables. System identity/credential/log tables are not touched. */
DROP TABLE IF EXISTS nexus.query_node;
DROP TABLE IF EXISTS nexus.query_stage;
DROP TABLE IF EXISTS nexus.query_run;
DROP TABLE IF EXISTS nexus.index_quality_metric;
DROP TABLE IF EXISTS nexus.index_node;
DROP TABLE IF EXISTS nexus.index_run;
DROP TABLE IF EXISTS nexus.graph_edge_support;
DROP TABLE IF EXISTS nexus.graph_edge;
DROP TABLE IF EXISTS nexus.assertion_evidence;
DROP TABLE IF EXISTS nexus.assertion_entity;
DROP TABLE IF EXISTS nexus.legal_assertion;
DROP TABLE IF EXISTS nexus.action_mention;
DROP TABLE IF EXISTS nexus.action_participant;
DROP TABLE IF EXISTS nexus.action;
DROP TABLE IF EXISTS nexus.entity_mention;
DROP TABLE IF EXISTS nexus.entity_alias;
DROP TABLE IF EXISTS nexus.entity;
DROP TABLE IF EXISTS nexus.block_extraction_attempt;
DROP TABLE IF EXISTS nexus.block_manifest;
DROP TABLE IF EXISTS nexus.document_version;
DROP TABLE IF EXISTS nexus.document;
DROP TABLE IF EXISTS nexus.index_generation;
DROP TABLE IF EXISTS nexus.evidence;
DROP TABLE IF EXISTS nexus.entity_edge;
DROP TABLE IF EXISTS nexus.run_node;
DROP TABLE IF EXISTS nexus.run_stage;
DROP TABLE IF EXISTS nexus.run;
DROP TABLE IF EXISTS nexus.collection_access;
DROP TABLE IF EXISTS nexus.collection_store;
DROP TABLE IF EXISTS nexus.collection;
DROP TABLE IF EXISTS nexus.search_store;
GO

/* ============================================================================
   Store / Collection configuration
   ============================================================================ */

CREATE TABLE nexus.search_store (
    store_id               nvarchar(64)   NOT NULL CONSTRAINT PK_search_store PRIMARY KEY,
    name                   nvarchar(200)  NOT NULL,
    credential_name        nvarchar(200)  NOT NULL,
    index_name             nvarchar(200)  NULL,
    kind                   nvarchar(20)   NOT NULL CONSTRAINT DF_store_kind DEFAULT 'block',
    active_generation_id   nvarchar(64)   NULL,
    is_default             bit            NOT NULL CONSTRAINT DF_store_default DEFAULT 0,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_store_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)   NOT NULL CONSTRAINT DF_store_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_store_kind CHECK (kind IN ('block'))
);
CREATE UNIQUE INDEX UX_store_one_default ON nexus.search_store(is_default) WHERE is_default = 1;
GO

CREATE TABLE nexus.collection (
    collection_id          nvarchar(64)   NOT NULL CONSTRAINT PK_collection PRIMARY KEY,
    name                   nvarchar(200)  NOT NULL,
    description            nvarchar(1000) NULL,
    is_public              bit            NOT NULL CONSTRAINT DF_collection_public DEFAULT 0,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_collection_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)   NOT NULL CONSTRAINT DF_collection_updated DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE nexus.collection_store (
    collection_id          nvarchar(64) NOT NULL,
    store_id               nvarchar(64) NOT NULL,
    CONSTRAINT PK_collection_store PRIMARY KEY (collection_id, store_id)
);
CREATE INDEX IX_collection_store_store ON nexus.collection_store(store_id, collection_id);
GO

CREATE TABLE nexus.collection_access (
    collection_id          nvarchar(64)  NOT NULL,
    principal_type         nvarchar(20)  NOT NULL,
    principal_id           nvarchar(256) NOT NULL,
    is_default             bit           NOT NULL CONSTRAINT DF_collection_access_default DEFAULT 0,
    created_at             datetime2(3)  NOT NULL CONSTRAINT DF_collection_access_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_collection_access PRIMARY KEY (collection_id, principal_type, principal_id),
    CONSTRAINT CK_collection_access_principal CHECK (principal_type IN ('user', 'role'))
);
CREATE INDEX IX_collection_access_principal
    ON nexus.collection_access(principal_type, principal_id, collection_id);
CREATE UNIQUE INDEX UX_collection_access_one_default
    ON nexus.collection_access(principal_type, principal_id)
    WHERE is_default = 1;
GO

/* ============================================================================
   Isolated index generations and document/block manifests
   ============================================================================ */

CREATE TABLE nexus.index_generation (
    generation_id          nvarchar(64)  NOT NULL CONSTRAINT PK_index_generation PRIMARY KEY,
    run_id                 nvarchar(64)  NOT NULL,
    store_id               nvarchar(64)  NOT NULL,
    base_generation_id     nvarchar(64)  NULL,
    state                  nvarchar(20)  NOT NULL CONSTRAINT DF_generation_state DEFAULT 'building',
    quality_state          nvarchar(20)  NOT NULL CONSTRAINT DF_generation_quality DEFAULT 'pending',
    ontology_version       nvarchar(50)  NOT NULL,
    extractor_version      nvarchar(50)  NOT NULL,
    embedding_dimensions   int           NOT NULL,
    document_count         int           NOT NULL CONSTRAINT DF_generation_docs DEFAULT 0,
    block_count            int           NOT NULL CONSTRAINT DF_generation_blocks DEFAULT 0,
    entity_count           int           NOT NULL CONSTRAINT DF_generation_entities DEFAULT 0,
    action_count           int           NOT NULL CONSTRAINT DF_generation_actions DEFAULT 0,
    assertion_count        int           NOT NULL CONSTRAINT DF_generation_assertions DEFAULT 0,
    graph_edge_count       int           NOT NULL CONSTRAINT DF_generation_edges DEFAULT 0,
    quality_summary        nvarchar(max) NULL,
    created_at             datetime2(3)  NOT NULL CONSTRAINT DF_generation_created DEFAULT SYSUTCDATETIME(),
    validated_at           datetime2(3)  NULL,
    activated_at           datetime2(3)  NULL,
    retired_at             datetime2(3)  NULL,
    CONSTRAINT UQ_generation_run UNIQUE (run_id),
    CONSTRAINT CK_generation_state CHECK (
        state IN ('building', 'validating', 'active', 'failed', 'cancelled', 'retired')
    ),
    CONSTRAINT CK_generation_quality CHECK (quality_state IN ('pending', 'passed', 'failed')),
    CONSTRAINT CK_generation_quality_json CHECK (quality_summary IS NULL OR ISJSON(quality_summary) = 1),
    CONSTRAINT CK_generation_dimensions CHECK (embedding_dimensions > 0)
);
CREATE INDEX IX_generation_store_state ON nexus.index_generation(store_id, state, created_at DESC);
CREATE INDEX IX_generation_base ON nexus.index_generation(store_id, base_generation_id, created_at DESC);
CREATE UNIQUE INDEX UX_generation_one_active_store
    ON nexus.index_generation(store_id)
    WHERE state = 'active';
GO

CREATE TABLE nexus.document (
    document_id            nvarchar(256)  NOT NULL CONSTRAINT PK_document PRIMARY KEY,
    canonical_title        nvarchar(400)  NOT NULL,
    category               nvarchar(100)  NOT NULL,
    source_uri             nvarchar(1000) NULL,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_document_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)   NOT NULL CONSTRAINT DF_document_updated DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_document_category ON nexus.document(category, canonical_title);
GO

CREATE TABLE nexus.document_version (
    document_version_id    nvarchar(64)   NOT NULL CONSTRAINT PK_document_version PRIMARY KEY,
    generation_id          nvarchar(64)   NOT NULL,
    document_id            nvarchar(256)  NOT NULL,
    title                  nvarchar(400)  NOT NULL,
    category               nvarchar(100)  NOT NULL,
    source_uri             nvarchar(1000) NULL,
    content_hash           char(64)       NOT NULL,
    block_count            int            NOT NULL CONSTRAINT DF_document_version_blocks DEFAULT 0,
    state                  nvarchar(20)   NOT NULL CONSTRAINT DF_document_version_state DEFAULT 'staged',
    raw_metadata           nvarchar(max)  NULL,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_document_version_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_document_version_generation UNIQUE (generation_id, document_id),
    CONSTRAINT CK_document_version_state CHECK (state IN ('staged', 'validated', 'rejected')),
    CONSTRAINT CK_document_version_metadata CHECK (raw_metadata IS NULL OR ISJSON(raw_metadata) = 1),
    CONSTRAINT CK_document_version_blocks CHECK (block_count >= 0)
);
CREATE INDEX IX_document_version_document ON nexus.document_version(document_id, generation_id);
CREATE INDEX IX_document_version_generation ON nexus.document_version(generation_id, state);
GO

CREATE TABLE nexus.block_manifest (
    block_key              nvarchar(450)  NOT NULL CONSTRAINT PK_block_manifest PRIMARY KEY,
    generation_id          nvarchar(64)   NOT NULL,
    document_version_id    nvarchar(64)   NOT NULL,
    document_id            nvarchar(256)  NOT NULL,
    block_id               nvarchar(450)  NOT NULL,
    parent_block_id        nvarchar(450)  NULL,
    article_no             nvarchar(50)   NULL,
    paragraph_no           nvarchar(50)   NULL,
    item_no                nvarchar(50)   NULL,
    heading_path           nvarchar(1000) NULL,
    ordinal                int            NOT NULL,
    text_hash              char(64)       NOT NULL,
    char_count             int            NOT NULL,
    extraction_state       nvarchar(20)   NOT NULL CONSTRAINT DF_block_extraction DEFAULT 'pending',
    search_state           nvarchar(20)   NOT NULL CONSTRAINT DF_block_search DEFAULT 'pending',
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_block_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_block_generation_id UNIQUE (generation_id, block_id),
    CONSTRAINT CK_block_ordinal CHECK (ordinal > 0),
    CONSTRAINT CK_block_char_count CHECK (char_count >= 0),
    CONSTRAINT CK_block_extraction_state CHECK (
        extraction_state IN ('pending', 'succeeded', 'empty', 'quarantined', 'failed')
    ),
    CONSTRAINT CK_block_search_state CHECK (search_state IN ('pending', 'written', 'failed'))
);
CREATE INDEX IX_block_generation ON nexus.block_manifest(generation_id, document_version_id, ordinal);
CREATE INDEX IX_block_document ON nexus.block_manifest(document_id, generation_id, ordinal);
CREATE INDEX IX_block_quality ON nexus.block_manifest(generation_id, extraction_state, search_state);
GO

CREATE TABLE nexus.block_extraction_attempt (
    attempt_id             bigint          IDENTITY(1,1) CONSTRAINT PK_block_extraction_attempt PRIMARY KEY,
    run_id                 nvarchar(64)     NOT NULL,
    generation_id          nvarchar(64)     NOT NULL,
    block_key              nvarchar(450)    NOT NULL,
    attempt_no             smallint         NOT NULL,
    state                  nvarchar(20)     NOT NULL,
    prompt_version         nvarchar(50)     NOT NULL,
    raw_output             nvarchar(max)    NULL,
    validation_errors      nvarchar(max)    NULL,
    tokens                 nvarchar(1000)   NULL,
    cost_ms                int              NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_extraction_attempt_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_extraction_attempt UNIQUE (run_id, block_key, attempt_no),
    CONSTRAINT CK_extraction_attempt_no CHECK (attempt_no > 0),
    CONSTRAINT CK_extraction_attempt_state CHECK (
        state IN ('succeeded', 'empty', 'quarantined', 'invalid', 'failed')
    ),
    CONSTRAINT CK_extraction_attempt_errors CHECK (
        validation_errors IS NULL OR ISJSON(validation_errors) = 1
    ),
    CONSTRAINT CK_extraction_attempt_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1)
);
CREATE INDEX IX_extraction_attempt_block ON nexus.block_extraction_attempt(generation_id, block_key, attempt_no);
CREATE INDEX IX_extraction_attempt_state ON nexus.block_extraction_attempt(run_id, state);
GO

/* ============================================================================
   Stable entities and contextual mentions
   ============================================================================ */

CREATE TABLE nexus.entity (
    entity_id              nvarchar(64)   NOT NULL CONSTRAINT PK_entity PRIMARY KEY,
    entity_type            nvarchar(30)   NOT NULL,
    canonical_name         nvarchar(400)  NOT NULL,
    normalized_name        nvarchar(400)  NOT NULL,
    description            nvarchar(2000) NULL,
    legal_status           nvarchar(30)   NULL,
    lifecycle_state        nvarchar(20)   NOT NULL CONSTRAINT DF_entity_lifecycle DEFAULT 'candidate',
    created_generation_id  nvarchar(64)   NULL,
    source                 nvarchar(20)   NOT NULL CONSTRAINT DF_entity_source DEFAULT 'llm',
    locked                 bit            NOT NULL CONSTRAINT DF_entity_locked DEFAULT 0,
    attrs                  nvarchar(max)  NULL,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_entity_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)   NOT NULL CONSTRAINT DF_entity_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_entity_type CHECK (
        entity_type IN ('Reg', 'Org', 'Activity', 'Product', 'Category', 'Concept')
    ),
    CONSTRAINT CK_entity_lifecycle CHECK (lifecycle_state IN ('candidate', 'active', 'rejected')),
    CONSTRAINT CK_entity_source CHECK (source IN ('llm', 'manual', 'seed')),
    CONSTRAINT CK_entity_attrs CHECK (attrs IS NULL OR ISJSON(attrs) = 1)
);
CREATE INDEX IX_entity_lookup ON nexus.entity(entity_type, normalized_name, lifecycle_state);
CREATE INDEX IX_entity_generation ON nexus.entity(created_generation_id, lifecycle_state);
GO

CREATE TABLE nexus.entity_alias (
    alias_id               bigint          IDENTITY(1,1) CONSTRAINT PK_entity_alias PRIMARY KEY,
    entity_id              nvarchar(64)     NOT NULL,
    generation_id          nvarchar(64)     NULL,
    alias                  nvarchar(400)    NOT NULL,
    normalized_alias       nvarchar(400)    NOT NULL,
    source                 nvarchar(20)     NOT NULL CONSTRAINT DF_entity_alias_source DEFAULT 'llm',
    confidence             decimal(5,4)     NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_entity_alias_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_entity_alias UNIQUE (entity_id, generation_id, normalized_alias),
    CONSTRAINT CK_entity_alias_source CHECK (source IN ('llm', 'manual', 'seed')),
    CONSTRAINT CK_entity_alias_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);
CREATE INDEX IX_entity_alias_lookup ON nexus.entity_alias(normalized_alias, generation_id, entity_id);
GO

CREATE TABLE nexus.entity_mention (
    mention_id             bigint          IDENTITY(1,1) CONSTRAINT PK_entity_mention PRIMARY KEY,
    generation_id          nvarchar(64)     NOT NULL,
    document_version_id    nvarchar(64)     NOT NULL,
    block_key              nvarchar(450)    NOT NULL,
    local_id               nvarchar(64)     NOT NULL,
    mention_text           nvarchar(1000)   NOT NULL,
    canonical_name         nvarchar(400)    NOT NULL,
    entity_type            nvarchar(30)     NOT NULL,
    start_offset           int              NULL,
    end_offset             int              NULL,
    entity_id              nvarchar(64)     NULL,
    resolution_state       nvarchar(20)     NOT NULL CONSTRAINT DF_entity_mention_state DEFAULT 'pending',
    confidence             decimal(5,4)     NULL,
    candidates             nvarchar(max)    NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_entity_mention_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_entity_mention_local UNIQUE (generation_id, block_key, local_id),
    CONSTRAINT CK_entity_mention_type CHECK (
        entity_type IN ('Reg', 'Org', 'Activity', 'Product', 'Category', 'Concept')
    ),
    CONSTRAINT CK_entity_mention_resolution CHECK (
        resolution_state IN ('pending', 'matched', 'new', 'ambiguous', 'rejected')
    ),
    CONSTRAINT CK_entity_mention_offsets CHECK (
        (start_offset IS NULL AND end_offset IS NULL)
        OR (start_offset >= 0 AND end_offset > start_offset)
    ),
    CONSTRAINT CK_entity_mention_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT CK_entity_mention_candidates CHECK (candidates IS NULL OR ISJSON(candidates) = 1)
);
CREATE INDEX IX_entity_mention_entity ON nexus.entity_mention(entity_id, generation_id);
CREATE INDEX IX_entity_mention_block ON nexus.entity_mention(generation_id, block_key);
CREATE INDEX IX_entity_mention_resolution ON nexus.entity_mention(generation_id, resolution_state);
GO

/* ============================================================================
   Normalized actions and action mentions
   ============================================================================ */

CREATE TABLE nexus.action (
    action_id              nvarchar(64)   NOT NULL CONSTRAINT PK_action PRIMARY KEY,
    canonical_text         nvarchar(1000) NOT NULL,
    verb                   nvarchar(200)  NOT NULL,
    signature_hash         char(64)       NOT NULL,
    lifecycle_state        nvarchar(20)   NOT NULL CONSTRAINT DF_action_lifecycle DEFAULT 'candidate',
    created_generation_id  nvarchar(64)   NULL,
    attrs                  nvarchar(max)  NULL,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_action_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)   NOT NULL CONSTRAINT DF_action_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_action_signature UNIQUE (signature_hash),
    CONSTRAINT CK_action_lifecycle CHECK (lifecycle_state IN ('candidate', 'active', 'rejected')),
    CONSTRAINT CK_action_attrs CHECK (attrs IS NULL OR ISJSON(attrs) = 1)
);
CREATE INDEX IX_action_verb ON nexus.action(verb, lifecycle_state);
CREATE INDEX IX_action_generation ON nexus.action(created_generation_id, lifecycle_state);
GO

CREATE TABLE nexus.action_participant (
    action_id              nvarchar(64)   NOT NULL,
    role                   nvarchar(30)   NOT NULL,
    ordinal                smallint       NOT NULL CONSTRAINT DF_action_participant_ordinal DEFAULT 1,
    entity_id              nvarchar(64)   NULL,
    value_text             nvarchar(1000) NULL,
    CONSTRAINT PK_action_participant PRIMARY KEY (action_id, role, ordinal),
    CONSTRAINT CK_action_participant_role CHECK (
        role IN ('object', 'recipient', 'authority', 'beneficiary', 'instrument', 'target')
    ),
    CONSTRAINT CK_action_participant_value CHECK (entity_id IS NOT NULL OR value_text IS NOT NULL),
    CONSTRAINT CK_action_participant_ordinal CHECK (ordinal > 0)
);
CREATE INDEX IX_action_participant_entity ON nexus.action_participant(entity_id, role, action_id);
GO

CREATE TABLE nexus.action_mention (
    action_mention_id      bigint          IDENTITY(1,1) CONSTRAINT PK_action_mention PRIMARY KEY,
    generation_id          nvarchar(64)     NOT NULL,
    document_version_id    nvarchar(64)     NOT NULL,
    block_key              nvarchar(450)    NOT NULL,
    local_id               nvarchar(64)     NOT NULL,
    canonical_text         nvarchar(1000)   NOT NULL,
    verb                   nvarchar(200)    NOT NULL,
    signature              nvarchar(max)    NOT NULL,
    action_id              nvarchar(64)     NULL,
    resolution_state       nvarchar(20)     NOT NULL CONSTRAINT DF_action_mention_state DEFAULT 'pending',
    confidence             decimal(5,4)     NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_action_mention_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_action_mention_local UNIQUE (generation_id, block_key, local_id),
    CONSTRAINT CK_action_mention_resolution CHECK (
        resolution_state IN ('pending', 'matched', 'new', 'ambiguous', 'rejected')
    ),
    CONSTRAINT CK_action_mention_signature CHECK (ISJSON(signature) = 1),
    CONSTRAINT CK_action_mention_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);
CREATE INDEX IX_action_mention_action ON nexus.action_mention(action_id, generation_id);
CREATE INDEX IX_action_mention_block ON nexus.action_mention(generation_id, block_key);
CREATE INDEX IX_action_mention_resolution ON nexus.action_mention(generation_id, resolution_state);
GO

/* ============================================================================
   Atomic legal assertions and provenance
   ============================================================================ */

CREATE TABLE nexus.legal_assertion (
    assertion_id           nvarchar(64)   NOT NULL CONSTRAINT PK_legal_assertion PRIMARY KEY,
    generation_id          nvarchar(64)   NOT NULL,
    document_version_id    nvarchar(64)   NOT NULL,
    assertion_kind         nvarchar(30)   NOT NULL,
    predicate              nvarchar(50)   NOT NULL,
    modality               nvarchar(30)   NOT NULL,
    action_id              nvarchar(64)   NULL,
    condition_text         nvarchar(max)  NULL,
    exception_text         nvarchar(max)  NULL,
    scope_text             nvarchar(max)  NULL,
    payload                nvarchar(max)  NULL,
    assertion_hash         char(64)       NOT NULL,
    confidence             decimal(5,4)   NOT NULL,
    state                  nvarchar(20)   NOT NULL CONSTRAINT DF_assertion_state DEFAULT 'accepted',
    source                 nvarchar(20)   NOT NULL CONSTRAINT DF_assertion_source DEFAULT 'llm',
    locked                 bit            NOT NULL CONSTRAINT DF_assertion_locked DEFAULT 0,
    created_at             datetime2(3)   NOT NULL CONSTRAINT DF_assertion_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_assertion_generation_hash UNIQUE (generation_id, assertion_hash),
    CONSTRAINT CK_assertion_kind CHECK (
        assertion_kind IN ('norm', 'definition', 'relation', 'deadline', 'penalty')
    ),
    CONSTRAINT CK_assertion_modality CHECK (
        modality IN ('must', 'must_not', 'may', 'should', 'factual', 'conditional_may')
    ),
    CONSTRAINT CK_assertion_state CHECK (state IN ('accepted', 'review', 'rejected')),
    CONSTRAINT CK_assertion_source CHECK (source IN ('llm', 'manual', 'seed')),
    CONSTRAINT CK_assertion_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT CK_assertion_payload CHECK (payload IS NULL OR ISJSON(payload) = 1)
);
CREATE INDEX IX_assertion_generation ON nexus.legal_assertion(generation_id, state, assertion_kind);
CREATE INDEX IX_assertion_action ON nexus.legal_assertion(action_id, generation_id, modality, state);
CREATE INDEX IX_assertion_document ON nexus.legal_assertion(document_version_id, generation_id, state);
CREATE INDEX IX_assertion_predicate ON nexus.legal_assertion(predicate, modality, generation_id, state);
GO

CREATE TABLE nexus.assertion_entity (
    assertion_id           nvarchar(64)   NOT NULL,
    role                   nvarchar(30)   NOT NULL,
    ordinal                smallint       NOT NULL CONSTRAINT DF_assertion_entity_ordinal DEFAULT 1,
    entity_id              nvarchar(64)   NULL,
    mention_id             bigint         NULL,
    value_text             nvarchar(1000) NOT NULL,
    CONSTRAINT PK_assertion_entity PRIMARY KEY (assertion_id, role, ordinal),
    CONSTRAINT CK_assertion_entity_role CHECK (
        role IN (
            'subject', 'object', 'recipient', 'authority', 'beneficiary',
            'regulation', 'activity', 'product', 'term'
        )
    ),
    CONSTRAINT CK_assertion_entity_ordinal CHECK (ordinal > 0)
);
CREATE INDEX IX_assertion_entity_lookup ON nexus.assertion_entity(entity_id, role, assertion_id);
CREATE INDEX IX_assertion_entity_mention ON nexus.assertion_entity(mention_id, assertion_id);
GO

CREATE TABLE nexus.assertion_evidence (
    evidence_id            bigint          IDENTITY(1,1) CONSTRAINT PK_assertion_evidence PRIMARY KEY,
    assertion_id           nvarchar(64)     NOT NULL,
    block_key              nvarchar(450)    NOT NULL,
    evidence_role          nvarchar(20)     NOT NULL CONSTRAINT DF_assertion_evidence_role DEFAULT 'primary',
    quote                  nvarchar(max)    NOT NULL,
    quote_start            int              NOT NULL,
    quote_end              int              NOT NULL,
    confidence             decimal(5,4)     NOT NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_assertion_evidence_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_assertion_evidence UNIQUE (assertion_id, block_key, evidence_role, quote_start),
    CONSTRAINT CK_assertion_evidence_role CHECK (evidence_role IN ('primary', 'supporting')),
    CONSTRAINT CK_assertion_evidence_offsets CHECK (quote_start >= 0 AND quote_end > quote_start),
    CONSTRAINT CK_assertion_evidence_quote CHECK (LEN(quote) > 0),
    CONSTRAINT CK_assertion_evidence_confidence CHECK (confidence BETWEEN 0 AND 1)
);
CREATE UNIQUE INDEX UX_assertion_one_primary
    ON nexus.assertion_evidence(assertion_id)
    WHERE evidence_role = 'primary';
CREATE INDEX IX_assertion_evidence_block ON nexus.assertion_evidence(block_key, assertion_id);
GO

/* ============================================================================
   Materialized navigation graph (derived from accepted assertions)
   ============================================================================ */

CREATE TABLE nexus.graph_edge (
    edge_id                bigint          IDENTITY(1,1) CONSTRAINT PK_graph_edge PRIMARY KEY,
    generation_id          nvarchar(64)     NOT NULL,
    src_kind               nvarchar(20)     NOT NULL,
    src_id                 nvarchar(64)     NOT NULL,
    edge_type              nvarchar(50)     NOT NULL,
    dst_kind               nvarchar(20)     NOT NULL,
    dst_id                 nvarchar(64)     NOT NULL,
    weight                 decimal(8,6)     NOT NULL CONSTRAINT DF_graph_edge_weight DEFAULT 1,
    source                 nvarchar(20)     NOT NULL CONSTRAINT DF_graph_edge_source DEFAULT 'derived',
    locked                 bit              NOT NULL CONSTRAINT DF_graph_edge_locked DEFAULT 0,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_graph_edge_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_graph_edge UNIQUE (
        generation_id, src_kind, src_id, edge_type, dst_kind, dst_id
    ),
    CONSTRAINT CK_graph_edge_src_kind CHECK (src_kind IN ('entity', 'action')),
    CONSTRAINT CK_graph_edge_dst_kind CHECK (dst_kind IN ('entity', 'action')),
    CONSTRAINT CK_graph_edge_weight CHECK (weight BETWEEN 0 AND 1),
    CONSTRAINT CK_graph_edge_source CHECK (source IN ('derived', 'manual'))
);
CREATE INDEX IX_graph_edge_src ON nexus.graph_edge(generation_id, src_kind, src_id, edge_type);
CREATE INDEX IX_graph_edge_dst ON nexus.graph_edge(generation_id, dst_kind, dst_id, edge_type);
CREATE INDEX IX_graph_edge_type ON nexus.graph_edge(generation_id, edge_type);
GO

CREATE TABLE nexus.graph_edge_support (
    edge_id                bigint        NOT NULL,
    assertion_id           nvarchar(64)  NOT NULL,
    created_at             datetime2(3)  NOT NULL CONSTRAINT DF_graph_support_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_graph_edge_support PRIMARY KEY (edge_id, assertion_id)
);
CREATE INDEX IX_graph_support_assertion ON nexus.graph_edge_support(assertion_id, edge_id);
GO

/* ============================================================================
   Index workflow runs and built-in quality gate
   ============================================================================ */

CREATE TABLE nexus.index_run (
    run_id                 nvarchar(64)  NOT NULL CONSTRAINT PK_index_run PRIMARY KEY,
    generation_id          nvarchar(64)  NULL,
    as_user                nvarchar(256) NULL,
    store_id               nvarchar(64)  NOT NULL,
    category               nvarchar(100) NULL,
    llm_credential         nvarchar(200) NOT NULL,
    embedding_credential   nvarchar(200) NOT NULL,
    max_parallel           int           NOT NULL CONSTRAINT DF_index_run_parallel DEFAULT 8,
    state                  nvarchar(20)  NOT NULL CONSTRAINT DF_index_run_state DEFAULT 'running',
    current_phase          nvarchar(40)  NULL,
    document_count         int           NOT NULL CONSTRAINT DF_index_run_documents DEFAULT 0,
    block_count            int           NOT NULL CONSTRAINT DF_index_run_blocks DEFAULT 0,
    entity_count           int           NOT NULL CONSTRAINT DF_index_run_entities DEFAULT 0,
    action_count           int           NOT NULL CONSTRAINT DF_index_run_actions DEFAULT 0,
    assertion_count        int           NOT NULL CONSTRAINT DF_index_run_assertions DEFAULT 0,
    graph_edge_count       int           NOT NULL CONSTRAINT DF_index_run_edges DEFAULT 0,
    quality_issue_count    int           NOT NULL CONSTRAINT DF_index_run_issues DEFAULT 0,
    node_count             int           NOT NULL CONSTRAINT DF_index_run_nodes DEFAULT 0,
    tokens                 nvarchar(1000) NULL,
    dag                    nvarchar(max) NULL,
    input_snapshot         nvarchar(max) NULL,
    error                  nvarchar(max) NULL,
    cost_ms                int           NOT NULL CONSTRAINT DF_index_run_cost DEFAULT 0,
    created_at             datetime2(3)  NOT NULL CONSTRAINT DF_index_run_created DEFAULT SYSUTCDATETIME(),
    updated_at             datetime2(3)  NOT NULL CONSTRAINT DF_index_run_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_index_run_state CHECK (state IN ('running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT CK_index_run_parallel CHECK (max_parallel > 0),
    CONSTRAINT CK_index_run_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1),
    CONSTRAINT CK_index_run_dag CHECK (dag IS NULL OR ISJSON(dag) = 1),
    CONSTRAINT CK_index_run_input CHECK (input_snapshot IS NULL OR ISJSON(input_snapshot) = 1)
);
CREATE INDEX IX_index_run_user ON nexus.index_run(as_user, created_at DESC);
CREATE INDEX IX_index_run_store ON nexus.index_run(store_id, created_at DESC);
CREATE INDEX IX_index_run_generation ON nexus.index_run(generation_id);
GO

CREATE TABLE nexus.index_node (
    run_id                 nvarchar(64)  NOT NULL,
    node_id                nvarchar(120) NOT NULL,
    state                  nvarchar(20)  NOT NULL CONSTRAINT DF_index_node_state DEFAULT 'pending',
    op                     nvarchar(50)  NULL,
    [input]                nvarchar(max) NULL,
    [output]               nvarchar(max) NULL,
    [value]                nvarchar(max) NULL,
    tokens                 nvarchar(1000) NULL,
    error                  nvarchar(max) NULL,
    cost_ms                int           NULL,
    started_at             datetime2(3)  NULL,
    ended_at               datetime2(3)  NULL,
    CONSTRAINT PK_index_node PRIMARY KEY (run_id, node_id),
    CONSTRAINT CK_index_node_state CHECK (
        state IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')
    ),
    CONSTRAINT CK_index_node_input CHECK ([input] IS NULL OR ISJSON([input]) = 1),
    CONSTRAINT CK_index_node_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1)
);
CREATE INDEX IX_index_node_run ON nexus.index_node(run_id, state, started_at);
GO

CREATE TABLE nexus.index_quality_metric (
    metric_id              bigint          IDENTITY(1,1) CONSTRAINT PK_index_quality_metric PRIMARY KEY,
    run_id                 nvarchar(64)     NOT NULL,
    generation_id          nvarchar(64)     NOT NULL,
    metric_code            nvarchar(100)    NOT NULL,
    scope_type             nvarchar(30)     NOT NULL CONSTRAINT DF_quality_scope DEFAULT 'generation',
    scope_id               nvarchar(450)    NULL,
    severity               nvarchar(20)     NOT NULL,
    passed                 bit              NOT NULL,
    actual_value           decimal(20,6)    NULL,
    threshold_value        decimal(20,6)    NULL,
    details                nvarchar(max)    NULL,
    created_at             datetime2(3)     NOT NULL CONSTRAINT DF_quality_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_quality_scope CHECK (
        scope_type IN ('generation', 'document', 'block', 'entity', 'action', 'assertion', 'graph_edge')
    ),
    CONSTRAINT CK_quality_severity CHECK (severity IN ('info', 'warning', 'error')),
    CONSTRAINT CK_quality_details CHECK (details IS NULL OR ISJSON(details) = 1)
);
CREATE INDEX IX_quality_run ON nexus.index_quality_metric(run_id, severity, passed);
CREATE INDEX IX_quality_generation ON nexus.index_quality_metric(generation_id, metric_code, passed);
GO

/* ============================================================================
   Five-stage query runs and PEP node execution
   ============================================================================ */

CREATE TABLE nexus.query_run (
    run_id                  nvarchar(64)  NOT NULL CONSTRAINT PK_query_run PRIMARY KEY,
    as_user                 nvarchar(256) NULL,
    question                nvarchar(max) NOT NULL,
    collection_id           nvarchar(64)  NULL,
    collection_name         nvarchar(200) NULL,
    collection_selected_by  nvarchar(30)  NULL,
    allowed_stores          nvarchar(max) NULL,
    generation_scope        nvarchar(max) NULL,
    llm_credential          nvarchar(200) NOT NULL,
    embedding_credential    nvarchar(200) NOT NULL,
    max_parallel            int           NOT NULL CONSTRAINT DF_query_run_parallel DEFAULT 8,
    budgets                 nvarchar(max) NULL,
    state                   nvarchar(20)  NOT NULL CONSTRAINT DF_query_run_state DEFAULT 'running',
    current_stage           nvarchar(30)  NULL,
    node_count              int           NOT NULL CONSTRAINT DF_query_run_nodes DEFAULT 0,
    tokens                  nvarchar(1000) NULL,
    answer                  nvarchar(max) NULL,
    citations               nvarchar(max) NULL,
    error                   nvarchar(max) NULL,
    cost_ms                 int           NOT NULL CONSTRAINT DF_query_run_cost DEFAULT 0,
    created_at              datetime2(3)  NOT NULL CONSTRAINT DF_query_run_created DEFAULT SYSUTCDATETIME(),
    updated_at              datetime2(3)  NOT NULL CONSTRAINT DF_query_run_updated DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_query_run_state CHECK (state IN ('running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT CK_query_run_parallel CHECK (max_parallel > 0),
    CONSTRAINT CK_query_run_stores CHECK (allowed_stores IS NULL OR ISJSON(allowed_stores) = 1),
    CONSTRAINT CK_query_run_generations CHECK (generation_scope IS NULL OR ISJSON(generation_scope) = 1),
    CONSTRAINT CK_query_run_budgets CHECK (budgets IS NULL OR ISJSON(budgets) = 1),
    CONSTRAINT CK_query_run_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1),
    CONSTRAINT CK_query_run_citations CHECK (citations IS NULL OR ISJSON(citations) = 1)
);
CREATE INDEX IX_query_run_user ON nexus.query_run(as_user, created_at DESC);
CREATE INDEX IX_query_run_collection ON nexus.query_run(collection_id, created_at DESC);
GO

CREATE TABLE nexus.query_stage (
    run_id                 nvarchar(64)  NOT NULL,
    stage_id               nvarchar(30)  NOT NULL,
    ordinal                tinyint       NOT NULL,
    name                   nvarchar(100) NOT NULL,
    state                  nvarchar(20)  NOT NULL CONSTRAINT DF_query_stage_state DEFAULT 'pending',
    [input]                nvarchar(max) NULL,
    [output]               nvarchar(max) NULL,
    tokens                 nvarchar(1000) NULL,
    error                  nvarchar(max) NULL,
    cost_ms                int           NULL,
    started_at             datetime2(3)  NULL,
    ended_at               datetime2(3)  NULL,
    CONSTRAINT PK_query_stage PRIMARY KEY (run_id, stage_id),
    CONSTRAINT UQ_query_stage_order UNIQUE (run_id, ordinal),
    CONSTRAINT CK_query_stage_id CHECK (
        stage_id IN ('initializer', 'compiler', 'optimizer', 'coordinator', 'generator')
    ),
    CONSTRAINT CK_query_stage_state CHECK (
        state IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')
    ),
    CONSTRAINT CK_query_stage_input CHECK ([input] IS NULL OR ISJSON([input]) = 1),
    CONSTRAINT CK_query_stage_output CHECK ([output] IS NULL OR ISJSON([output]) = 1),
    CONSTRAINT CK_query_stage_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1)
);
CREATE INDEX IX_query_stage_run ON nexus.query_stage(run_id, ordinal);
GO

CREATE TABLE nexus.query_node (
    run_id                 nvarchar(64)  NOT NULL,
    node_id                nvarchar(120) NOT NULL,
    state                  nvarchar(20)  NOT NULL CONSTRAINT DF_query_node_state DEFAULT 'pending',
    op                     nvarchar(50)  NOT NULL,
    [input]                nvarchar(max) NULL,
    [output]               nvarchar(max) NULL,
    [value]                nvarchar(max) NULL,
    tokens                 nvarchar(1000) NULL,
    error                  nvarchar(max) NULL,
    cost_ms                int           NULL,
    started_at             datetime2(3)  NULL,
    ended_at               datetime2(3)  NULL,
    CONSTRAINT PK_query_node PRIMARY KEY (run_id, node_id),
    CONSTRAINT CK_query_node_state CHECK (
        state IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')
    ),
    CONSTRAINT CK_query_node_input CHECK ([input] IS NULL OR ISJSON([input]) = 1),
    CONSTRAINT CK_query_node_output CHECK ([output] IS NULL OR ISJSON([output]) = 1),
    CONSTRAINT CK_query_node_tokens CHECK (tokens IS NULL OR ISJSON(tokens) = 1)
);
CREATE INDEX IX_query_node_run ON nexus.query_node(run_id, state, started_at);
GO

/* ============================================================================
   Application-enforced activation invariants

   - search_store.active_generation_id points to an active generation of that store.
   - accepted assertions have one primary evidence row and resolved participants.
   - graph edges have at least one graph_edge_support row.
   - failed/cancelled generations never become visible.
   - query initialization snapshots both allowed_stores and generation_scope.
   ============================================================================ */
