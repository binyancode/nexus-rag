/* Query v1 schema reset.
   当前 query 表尚未投入生产：直接重建为 run → stage → node，不迁移旧预留数据。
   执行一次后，日常部署继续使用 schema.sql。 */

IF COL_LENGTH('nexus.collection', 'is_public') IS NULL
    ALTER TABLE nexus.collection ADD is_public bit NOT NULL
        CONSTRAINT DF_coll_public_migration DEFAULT 0;
GO

IF OBJECT_ID('nexus.collection_access','U') IS NULL
BEGIN
    CREATE TABLE nexus.collection_access (
        collection_id  nvarchar(64)  NOT NULL,
        principal_type nvarchar(20)  NOT NULL,
        principal_id   nvarchar(256) NOT NULL,
        is_default     bit           NOT NULL CONSTRAINT DF_ca_default DEFAULT 0,
        created_at     datetime2     NOT NULL CONSTRAINT DF_ca_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_collection_access PRIMARY KEY (collection_id, principal_type, principal_id),
        CONSTRAINT CK_ca_principal_type CHECK (principal_type IN ('user','role'))
    );
    CREATE INDEX IX_ca_principal ON nexus.collection_access(principal_type, principal_id, collection_id);
    CREATE UNIQUE INDEX UX_ca_one_default
        ON nexus.collection_access(principal_type, principal_id)
        WHERE is_default = 1;
END;
GO

-- 现有 Collection 若无任何授权，显式设为公开，避免升级后所有用户突然不可见。
-- 上线前可按实际权限改为 is_public=0，并写 collection_access。
UPDATE c SET is_public=1
FROM nexus.collection c
WHERE NOT EXISTS (
    SELECT 1 FROM nexus.collection_access a WHERE a.collection_id=c.collection_id
);
GO

IF EXISTS (SELECT 1 FROM nexus.search_store) AND NOT EXISTS (SELECT 1 FROM nexus.collection)
BEGIN
    INSERT INTO nexus.collection(collection_id,name,description,is_public)
    VALUES ('default',N'默认法规库',N'系统首次启用查询时创建；可在后续管理功能中调整成员 Store',1);
    INSERT INTO nexus.collection_store(collection_id,store_id)
    SELECT 'default',store_id FROM nexus.search_store;
END;
GO

DROP TABLE IF EXISTS nexus.query_node;
DROP TABLE IF EXISTS nexus.query_stage;
DROP TABLE IF EXISTS nexus.query_run;
GO

CREATE TABLE nexus.query_run (
    run_id                  nvarchar(64)  NOT NULL CONSTRAINT PK_query_run PRIMARY KEY,
    as_user                 nvarchar(256) NULL,
    question                nvarchar(max) NOT NULL,
    collection_id           nvarchar(64)  NULL,
    collection_name         nvarchar(200) NULL,
    collection_selected_by  nvarchar(30)  NULL,
    allowed_stores          nvarchar(max) NULL,
    llm_credential          nvarchar(200) NOT NULL,
    embedding_credential    nvarchar(200) NOT NULL,
    max_parallel            int           NOT NULL CONSTRAINT DF_qrun_par DEFAULT 8,
    [state]                 nvarchar(20)  NOT NULL CONSTRAINT DF_qrun_state DEFAULT 'running',
    current_stage           nvarchar(30)  NULL,
    node_count              int           NOT NULL CONSTRAINT DF_qrun_node DEFAULT 0,
    tokens                  nvarchar(1000) NULL,
    answer                  nvarchar(max) NULL,
    citations               nvarchar(max) NULL,
    error                   nvarchar(max) NULL,
    cost_ms                 int           NOT NULL CONSTRAINT DF_qrun_cost DEFAULT 0,
    created_at              datetime2     NOT NULL CONSTRAINT DF_qrun_created DEFAULT SYSUTCDATETIME(),
    updated_at              datetime2     NOT NULL CONSTRAINT DF_qrun_updated DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_query_run_user ON nexus.query_run(as_user,created_at);
GO

CREATE TABLE nexus.query_stage (
    run_id      nvarchar(64)  NOT NULL,
    stage_id    nvarchar(30)  NOT NULL,
    ordinal     tinyint       NOT NULL,
    name        nvarchar(100) NOT NULL,
    [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_qstage_state DEFAULT 'pending',
    [input]     nvarchar(max) NULL,
    [output]    nvarchar(max) NULL,
    tokens      nvarchar(1000) NULL,
    error       nvarchar(max) NULL,
    cost_ms     int           NULL,
    started_at  datetime2     NULL,
    ended_at    datetime2     NULL,
    CONSTRAINT PK_query_stage PRIMARY KEY (run_id,stage_id),
    CONSTRAINT UQ_query_stage_order UNIQUE (run_id,ordinal),
    CONSTRAINT CK_query_stage_id CHECK (stage_id IN ('initializer','compiler','optimizer','coordinator','generator'))
);
CREATE INDEX IX_query_stage_run ON nexus.query_stage(run_id,ordinal);
GO

CREATE TABLE nexus.query_node (
    run_id      nvarchar(64)  NOT NULL,
    node_id     nvarchar(120) NOT NULL,
    [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_qnode_state DEFAULT 'running',
    op          nvarchar(50)  NOT NULL,
    [input]     nvarchar(max) NULL,
    [output]    nvarchar(max) NULL,
    [value]     nvarchar(max) NULL,
    tokens      nvarchar(1000) NULL,
    error       nvarchar(max) NULL,
    cost_ms     int           NULL,
    started_at  datetime2     NULL,
    ended_at    datetime2     NULL,
    CONSTRAINT PK_query_node PRIMARY KEY (run_id,node_id)
);
CREATE INDEX IX_query_node_run ON nexus.query_node(run_id,[state]);
GO
