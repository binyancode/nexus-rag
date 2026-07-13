/* ============================================================
   Nexus Retrieval Engine —— 数据库结构（SQL Server / Azure SQL）
   schema: nexus
   说明：
     - 块本体（原文 + 向量 + fullname + 元数据）存在 Azure AI Search，本库不存块内容。
     - 本库存：实体层、结构边、出处指针(entity↔块 fullname)、Store/Collection 注册、
              文档路由、运行记录。
     - 已存在的表：nexus.api_log / nexus.app_credential / nexus.app_user（此脚本不重建）。
   对应设计：§1.2 实体层、§1.3/§1.4 边、§1.5 attach_entity(source/locked)、§1.6 Store/Collection。
   幂等：可重复执行（IF OBJECT_ID 保护）。
   ============================================================ */

IF SCHEMA_ID('nexus') IS NULL EXEC('CREATE SCHEMA nexus');
GO

/* ==================== 迁移：移除 nexus 所有外键 ====================
   设计：不靠数据库外键/级联，删除顺序与范围全部由应用代码保证
        （覆盖=只删本次文档的块与出处，共享实体/边走 upsert 合并）。
   幂等：已存在的外键全部 DROP；新库无外键则空操作。 */
DECLARE @drop_fk nvarchar(max) = N'';
SELECT @drop_fk = @drop_fk
     + N'ALTER TABLE ' + QUOTENAME(SCHEMA_NAME(o.schema_id)) + N'.' + QUOTENAME(o.name)
     + N' DROP CONSTRAINT ' + QUOTENAME(fk.name) + N';' + CHAR(10)
FROM sys.foreign_keys fk
JOIN sys.objects o ON fk.parent_object_id = o.object_id
WHERE SCHEMA_NAME(o.schema_id) = 'nexus';
IF LEN(@drop_fk) > 0 EXEC sp_executesql @drop_fk;
GO

/* ==================== Store / Collection 注册（§1.6） ==================== */

-- 一个 store = 一条 azure_ai_search 凭据；块的物理落点（可多实例）
IF OBJECT_ID('nexus.search_store','U') IS NULL
BEGIN
    CREATE TABLE nexus.search_store (
        store_id         nvarchar(64)   NOT NULL CONSTRAINT PK_search_store PRIMARY KEY,
        name             nvarchar(200)  NOT NULL,
        credential_name  nvarchar(200)  NOT NULL,          -- → nexus.app_credential（azure_ai_search）
        index_name       nvarchar(200)  NULL,              -- 覆盖凭据里的默认索引
        kind             nvarchar(20)   NOT NULL CONSTRAINT DF_store_kind DEFAULT 'block',  -- block | entity
        is_default       bit            NOT NULL CONSTRAINT DF_store_default DEFAULT 0,
        created_at       datetime2      NOT NULL CONSTRAINT DF_store_created DEFAULT SYSUTCDATETIME(),
        updated_at       datetime2      NOT NULL CONSTRAINT DF_store_updated DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- collection = store 集合（查询作用域）；与 store 多对多，纯查询期过滤器
IF OBJECT_ID('nexus.collection','U') IS NULL
BEGIN
    CREATE TABLE nexus.collection (
        collection_id  nvarchar(64)   NOT NULL CONSTRAINT PK_collection PRIMARY KEY,
        name           nvarchar(200)  NOT NULL,
        description    nvarchar(1000) NULL,
        is_public      bit            NOT NULL CONSTRAINT DF_coll_public DEFAULT 0,
        created_at     datetime2      NOT NULL CONSTRAINT DF_coll_created DEFAULT SYSUTCDATETIME(),
        updated_at     datetime2      NOT NULL CONSTRAINT DF_coll_updated DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Collection 可见性：支持用户/角色授权；同一主体最多一个默认 Collection（由唯一过滤索引保证）
IF OBJECT_ID('nexus.collection_access','U') IS NULL
BEGIN
    CREATE TABLE nexus.collection_access (
        collection_id  nvarchar(64)  NOT NULL,
        principal_type nvarchar(20)  NOT NULL,   -- user | role
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

-- collection ↔ store 多对多（一个 store 可属多个 collection）
IF OBJECT_ID('nexus.collection_store','U') IS NULL
BEGIN
    CREATE TABLE nexus.collection_store (
        collection_id  nvarchar(64) NOT NULL,
        store_id       nvarchar(64) NOT NULL,
        CONSTRAINT PK_collection_store PRIMARY KEY (collection_id, store_id)
    );
    CREATE INDEX IX_cs_store ON nexus.collection_store(store_id);
END;
GO

-- 一期兜底：已有 Store 但尚未配置任何 Collection 时，建立真实的默认 Collection。
-- 一旦存在任意 Collection，本脚本不自动修改其成员关系。
IF EXISTS (SELECT 1 FROM nexus.search_store)
   AND NOT EXISTS (SELECT 1 FROM nexus.collection)
BEGIN
    INSERT INTO nexus.collection(collection_id, name, description, is_public)
    VALUES ('default', N'默认法规库', N'系统首次启用查询时创建；可在后续管理功能中调整成员 Store', 1);
    INSERT INTO nexus.collection_store(collection_id, store_id)
    SELECT 'default', store_id FROM nexus.search_store;
END;
GO

/* ==================== 文档注册（路由 + 增量，§1.5/§1.6） ==================== */

-- 记录 fullname 里的 文档_id → 落在哪个 block store（Ground 路由）；content_hash 支持增量
IF OBJECT_ID('nexus.document','U') IS NULL
BEGIN
    CREATE TABLE nexus.document (
        doc_id        nvarchar(256)  NOT NULL CONSTRAINT PK_document PRIMARY KEY,  -- fullname 里的 文档_id
        title         nvarchar(400)  NULL,
        category      nvarchar(100)  NULL,     -- fullname 里的 类别_id（如 IND / NDA / IIT）
        store_id      nvarchar(64)   NOT NULL, -- 该文档的块落在哪个 block store
        content_hash  char(64)       NULL,     -- 增量：hash 变了才重抽该文档
        source_uri    nvarchar(1000) NULL,
        block_count   int            NOT NULL CONSTRAINT DF_doc_blocks DEFAULT 0,
        created_at    datetime2      NOT NULL CONSTRAINT DF_doc_created DEFAULT SYSUTCDATETIME(),
        updated_at    datetime2      NOT NULL CONSTRAINT DF_doc_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_doc_store ON nexus.document(store_id);
END;
GO

/* ==================== 实体层（§1.2） ==================== */

-- 唯一去重的概念节点：entity_id = 类型:规范名（如 Reg:药品管理法 / AppType:IND）
IF OBJECT_ID('nexus.entity','U') IS NULL
BEGIN
    CREATE TABLE nexus.entity (
        entity_id   nvarchar(200)  NOT NULL CONSTRAINT PK_entity PRIMARY KEY,
        type        nvarchar(50)   NOT NULL,                 -- AppType | Reg | Category ...
        name        nvarchar(400)  NOT NULL,                 -- 规范名
        status      nvarchar(30)   NULL,                     -- 现行 / 废止 ...
        attrs       nvarchar(max)  NULL,                     -- JSON 扩展属性
        source      nvarchar(10)   NOT NULL CONSTRAINT DF_entity_source DEFAULT 'llm',  -- seed | manual | llm
        locked      bit            NOT NULL CONSTRAINT DF_entity_locked DEFAULT 0,
        created_at  datetime2      NOT NULL CONSTRAINT DF_entity_created DEFAULT SYSUTCDATETIME(),
        updated_at  datetime2      NOT NULL CONSTRAINT DF_entity_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_entity_type ON nexus.entity(type);
END;
GO

-- 别名（归一：GCP 的多种写法 → 同一个 Reg:GCP）
IF OBJECT_ID('nexus.entity_alias','U') IS NULL
BEGIN
    CREATE TABLE nexus.entity_alias (
        entity_id  nvarchar(200) NOT NULL,
        alias      nvarchar(400) NOT NULL,
        CONSTRAINT PK_entity_alias PRIMARY KEY (entity_id, alias)
    );
    CREATE INDEX IX_alias_alias ON nexus.entity_alias(alias);  -- 别名反查规范实体
END;
GO

/* ==================== 结构边：实体 ↔ 实体（§1.4） ==================== */

-- 有向、带类型、带权；关系只存一次（有向一行），反向靠遍历
IF OBJECT_ID('nexus.entity_edge','U') IS NULL
BEGIN
    CREATE TABLE nexus.entity_edge (
        edge_id        bigint         IDENTITY(1,1) CONSTRAINT PK_entity_edge PRIMARY KEY,
        src_entity_id  nvarchar(200)  NOT NULL,
        type           nvarchar(30)   NOT NULL,     -- requires | belongs_to | supersedes | references
        dst_entity_id  nvarchar(200)  NOT NULL,
        weight         float          NOT NULL CONSTRAINT DF_edge_weight DEFAULT 1.0,
        evidence       nvarchar(max)  NULL,         -- 佐证（支撑该边的 block fullname 列表/说明，JSON）
        source         nvarchar(10)   NOT NULL CONSTRAINT DF_edge_source DEFAULT 'llm',  -- seed | manual | llm
        locked         bit            NOT NULL CONSTRAINT DF_edge_locked DEFAULT 0,
        created_at     datetime2      NOT NULL CONSTRAINT DF_edge_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_entity_edge UNIQUE (src_entity_id, type, dst_entity_id)
    );
    CREATE INDEX IX_edge_dst  ON nexus.entity_edge(dst_entity_id, type);  -- 反向遍历“谁要求我”
    CREATE INDEX IX_edge_type ON nexus.entity_edge(type);
END;
GO

/* ==================== 出处边：实体 ↔ 块（跨层，带 store_id，§1.3/§1.6） ==================== */

-- 块本体在 AI Search；这里只存“实体 → 块 fullname”的指针 + store 归属（collection 过滤用）
IF OBJECT_ID('nexus.evidence','U') IS NULL
BEGIN
    CREATE TABLE nexus.evidence (
        evidence_id  bigint         IDENTITY(1,1) CONSTRAINT PK_evidence PRIMARY KEY,
        entity_id    nvarchar(200)  NOT NULL,
        fullname     nvarchar(450)  NOT NULL,      -- 块地址：类别.文档.章节.block
        store_id     nvarchar(64)   NOT NULL,      -- 块所在 store（allowed_stores 过滤）
        weight       float          NOT NULL CONSTRAINT DF_ev_weight DEFAULT 1.0,
        source       nvarchar(10)   NOT NULL CONSTRAINT DF_ev_source DEFAULT 'llm',
        locked       bit            NOT NULL CONSTRAINT DF_ev_locked DEFAULT 0,
        created_at   datetime2      NOT NULL CONSTRAINT DF_ev_created DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_evidence UNIQUE (entity_id, fullname)
    );
    CREATE INDEX IX_ev_entity   ON nexus.evidence(entity_id);
    CREATE INDEX IX_ev_store    ON nexus.evidence(store_id);   -- “实体在不在某 collection” = evidence.store_id ∈ 集合
    CREATE INDEX IX_ev_fullname ON nexus.evidence(fullname);
END;
GO

/* ==================== 运行记录：Workflow DAG（索引 / 检索 两套） ====================
   设计：
     - 通用 Workflow 引擎跑 DAG；索引与检索各写各的两套表（run + node）。
     - 结构（节点/边/sibling_group/phase/layer/depends_on）只存 *_run.dag（整图 JSON，
       虚拟节点展开时整体重写）；node 表只存单节点运行态（懒插入：开始执行才建行）。
     - token 用单个 JSON 列：{"input","output","cached","embedding"}（无 total，各维独立）。
   ==================================================================================== */

-- 弃用旧的通用 run 三件套（直接删，不迁移）
IF OBJECT_ID('nexus.run_node','U')  IS NOT NULL DROP TABLE nexus.run_node;
IF OBJECT_ID('nexus.run_stage','U') IS NOT NULL DROP TABLE nexus.run_stage;
IF OBJECT_ID('nexus.run','U')       IS NOT NULL DROP TABLE nexus.run;
GO

-- ===== 索引运行 =====
IF OBJECT_ID('nexus.index_run','U') IS NULL
BEGIN
    CREATE TABLE nexus.index_run (
        run_id                nvarchar(64)  NOT NULL CONSTRAINT PK_index_run PRIMARY KEY,
        as_user               nvarchar(256) NULL,
        store_id              nvarchar(64)  NULL,          -- 块落点（无 FK）
        category              nvarchar(100) NULL,          -- 进 fullname 的类别
        llm_credential        nvarchar(200) NULL,
        embedding_credential  nvarchar(200) NULL,
        max_parallel          int           NOT NULL CONSTRAINT DF_irun_par   DEFAULT 8,
        [state]               nvarchar(20)  NOT NULL CONSTRAINT DF_irun_state DEFAULT 'running', -- running|succeeded|failed
        doc_count             int           NOT NULL CONSTRAINT DF_irun_doc   DEFAULT 0,
        block_count           int           NOT NULL CONSTRAINT DF_irun_blk   DEFAULT 0,
        node_count            int           NOT NULL CONSTRAINT DF_irun_node  DEFAULT 0,
        tokens                nvarchar(1000) NULL,         -- JSON 聚合：{"input","output","cached","embedding"}
        dag                   nvarchar(max) NULL,          -- 完整 DAG 结构 JSON（展开时整体重写）
        error                 nvarchar(max) NULL,
        cost_ms               int           NOT NULL CONSTRAINT DF_irun_cost  DEFAULT 0,
        created_at            datetime2     NOT NULL CONSTRAINT DF_irun_created DEFAULT SYSUTCDATETIME(),
        updated_at            datetime2     NOT NULL CONSTRAINT DF_irun_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_index_run_user ON nexus.index_run(as_user, created_at);
END;
GO

-- DAG 每节点运行态（结构见 index_run.dag；懒插入）
IF OBJECT_ID('nexus.index_node','U') IS NULL
BEGIN
    CREATE TABLE nexus.index_node (
        run_id      nvarchar(64)  NOT NULL,
        node_id     nvarchar(120) NOT NULL,     -- 对应 dag JSON 的 id（如 extract#37）
        [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_inode_state DEFAULT 'running', -- running|succeeded|failed|skipped
        tokens      nvarchar(400) NULL,         -- JSON 本节点明细
        [output]    nvarchar(max) NULL,
        [value]     nvarchar(max) NULL,
        error       nvarchar(max) NULL,
        cost_ms     int           NULL,
        started_at  datetime2     NULL,
        ended_at    datetime2     NULL,
        CONSTRAINT PK_index_node PRIMARY KEY (run_id, node_id)
    );
    CREATE INDEX IX_index_node_run ON nexus.index_node(run_id, [state]);
END;
GO

-- ===== 检索运行：run（总体）→ stage（五个引擎）→ node（协调器执行的物理节点）=====
IF OBJECT_ID('nexus.query_run','U') IS NULL
BEGIN
    CREATE TABLE nexus.query_run (
        run_id                  nvarchar(64)  NOT NULL CONSTRAINT PK_query_run PRIMARY KEY,
        as_user                 nvarchar(256) NULL,
        question                nvarchar(max) NOT NULL,
        collection_id           nvarchar(64)  NULL,          -- 初始化器确定后写入
        collection_name         nvarchar(200) NULL,          -- 运行时名称快照
        collection_selected_by  nvarchar(30)  NULL,          -- user | user_default | only_visible | semantic_router
        allowed_stores          nvarchar(max) NULL,          -- 运行时 Store 范围 JSON 快照
        llm_credential          nvarchar(200) NOT NULL,
        embedding_credential    nvarchar(200) NOT NULL,
        max_parallel            int           NOT NULL CONSTRAINT DF_qrun_par DEFAULT 8,
        [state]                 nvarchar(20)  NOT NULL CONSTRAINT DF_qrun_state DEFAULT 'running',
        current_stage           nvarchar(30)  NULL,
        node_count              int           NOT NULL CONSTRAINT DF_qrun_node DEFAULT 0,
        tokens                  nvarchar(1000) NULL,
        answer                  nvarchar(max) NULL,
        citations               nvarchar(max) NULL,          -- JSON [{fullname,quote}]
        error                   nvarchar(max) NULL,
        cost_ms                 int           NOT NULL CONSTRAINT DF_qrun_cost DEFAULT 0,
        created_at              datetime2     NOT NULL CONSTRAINT DF_qrun_created DEFAULT SYSUTCDATETIME(),
        updated_at              datetime2     NOT NULL CONSTRAINT DF_qrun_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_query_run_user ON nexus.query_run(as_user, created_at);
END;
GO

-- 固定五阶段；input/output 保存阶段契约，便于历史恢复和排查
IF OBJECT_ID('nexus.query_stage','U') IS NULL
BEGIN
    CREATE TABLE nexus.query_stage (
        run_id      nvarchar(64)  NOT NULL,
        stage_id    nvarchar(30)  NOT NULL,    -- initializer | compiler | optimizer | coordinator | generator
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
        CONSTRAINT PK_query_stage PRIMARY KEY (run_id, stage_id),
        CONSTRAINT UQ_query_stage_order UNIQUE (run_id, ordinal),
        CONSTRAINT CK_query_stage_id CHECK (stage_id IN ('initializer','compiler','optimizer','coordinator','generator'))
    );
    CREATE INDEX IX_query_stage_run ON nexus.query_stage(run_id, ordinal);
END;
GO

-- 协调器执行 PEP 时的物理节点运行态
IF OBJECT_ID('nexus.query_node','U') IS NULL
BEGIN
    CREATE TABLE nexus.query_node (
        run_id      nvarchar(64)  NOT NULL,
        node_id     nvarchar(120) NOT NULL,
        [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_qnode_state DEFAULT 'running',
        op           nvarchar(50)  NOT NULL,
        [input]      nvarchar(max) NULL,
        [output]    nvarchar(max) NULL,
        [value]     nvarchar(max) NULL,
        tokens      nvarchar(1000) NULL,
        error       nvarchar(max) NULL,
        cost_ms     int           NULL,
        started_at  datetime2     NULL,
        ended_at    datetime2     NULL,
        CONSTRAINT PK_query_node PRIMARY KEY (run_id, node_id)
    );
    CREATE INDEX IX_query_node_run ON nexus.query_node(run_id, [state]);
END;
GO

/* ============================================================
   示例数据（按需取消注释）
   ------------------------------------------------------------
   -- 1) 注册一个 block store（引用凭据 ai-search-main）
   -- INSERT nexus.search_store(store_id, name, credential_name, index_name, kind, is_default)
   -- VALUES ('store_main', '主搜索库', 'ai-search-main', 'nexus-blocks', 'block', 1);
   --
   -- 2) 建一个 collection 并纳入该 store
   -- INSERT nexus.collection(collection_id, name) VALUES ('col_reg', '法规库');
   -- INSERT nexus.collection_store(collection_id, store_id) VALUES ('col_reg', 'store_main');
   --
   -- 3) 查询期：某 collection 允许的 store 集合
   -- SELECT store_id FROM nexus.collection_store WHERE collection_id = 'col_reg';
   --
   -- 4) “某实体在不在该 collection” = 它的 evidence 有没有落在 allowed_stores 里
   -- SELECT DISTINCT e.entity_id
   -- FROM nexus.evidence e
   -- WHERE e.store_id IN (SELECT store_id FROM nexus.collection_store WHERE collection_id = 'col_reg');
   ============================================================ */
