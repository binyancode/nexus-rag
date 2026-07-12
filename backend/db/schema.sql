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
        created_at     datetime2      NOT NULL CONSTRAINT DF_coll_created DEFAULT SYSUTCDATETIME(),
        updated_at     datetime2      NOT NULL CONSTRAINT DF_coll_updated DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- collection ↔ store 多对多（一个 store 可属多个 collection）
IF OBJECT_ID('nexus.collection_store','U') IS NULL
BEGIN
    CREATE TABLE nexus.collection_store (
        collection_id  nvarchar(64) NOT NULL,
        store_id       nvarchar(64) NOT NULL,
        CONSTRAINT PK_collection_store PRIMARY KEY (collection_id, store_id),
        CONSTRAINT FK_cs_collection FOREIGN KEY (collection_id) REFERENCES nexus.collection(collection_id) ON DELETE CASCADE,
        CONSTRAINT FK_cs_store      FOREIGN KEY (store_id)      REFERENCES nexus.search_store(store_id)   ON DELETE CASCADE
    );
    CREATE INDEX IX_cs_store ON nexus.collection_store(store_id);
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
        updated_at    datetime2      NOT NULL CONSTRAINT DF_doc_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_doc_store FOREIGN KEY (store_id) REFERENCES nexus.search_store(store_id)
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
        CONSTRAINT PK_entity_alias PRIMARY KEY (entity_id, alias),
        CONSTRAINT FK_alias_entity FOREIGN KEY (entity_id) REFERENCES nexus.entity(entity_id) ON DELETE CASCADE
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
        CONSTRAINT UQ_entity_edge UNIQUE (src_entity_id, type, dst_entity_id),
        CONSTRAINT FK_edge_src FOREIGN KEY (src_entity_id) REFERENCES nexus.entity(entity_id),
        CONSTRAINT FK_edge_dst FOREIGN KEY (dst_entity_id) REFERENCES nexus.entity(entity_id)
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
        CONSTRAINT UQ_evidence UNIQUE (entity_id, fullname),
        CONSTRAINT FK_ev_entity FOREIGN KEY (entity_id) REFERENCES nexus.entity(entity_id) ON DELETE CASCADE,
        CONSTRAINT FK_ev_store  FOREIGN KEY (store_id)  REFERENCES nexus.search_store(store_id)
    );
    CREATE INDEX IX_ev_entity   ON nexus.evidence(entity_id);
    CREATE INDEX IX_ev_store    ON nexus.evidence(store_id);   -- “实体在不在某 collection” = evidence.store_id ∈ 集合
    CREATE INDEX IX_ev_fullname ON nexus.evidence(fullname);
END;
GO

/* ==================== 运行记录（对齐 bootstrap.DbRunRecorder） ==================== */

IF OBJECT_ID('nexus.run','U') IS NULL
BEGIN
    CREATE TABLE nexus.run (
        run_id      nvarchar(64)  NOT NULL CONSTRAINT PK_run PRIMARY KEY,
        question    nvarchar(max) NULL,
        as_user     nvarchar(256) NULL,
        context     nvarchar(max) NULL,   -- 可存 SQG / PEP JSON（§3.7 透明）
        answer      nvarchar(max) NULL,
        [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_run_state DEFAULT 'running',
        cost_ms     int           NOT NULL CONSTRAINT DF_run_cost DEFAULT 0,
        created_at  datetime2     NOT NULL CONSTRAINT DF_run_created DEFAULT SYSUTCDATETIME(),
        updated_at  datetime2     NOT NULL CONSTRAINT DF_run_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_run_user ON nexus.run(as_user, created_at);
END;
GO

IF OBJECT_ID('nexus.run_stage','U') IS NULL
BEGIN
    CREATE TABLE nexus.run_stage (
        run_id     nvarchar(64)  NOT NULL,
        stage      nvarchar(50)  NOT NULL,   -- compile / optimize / execute ...
        seq        int           NOT NULL CONSTRAINT DF_stage_seq DEFAULT 0,
        [state]    nvarchar(20)  NOT NULL CONSTRAINT DF_stage_state DEFAULT 'running',
        [input]    nvarchar(max) NULL,
        [output]   nvarchar(max) NULL,
        error      nvarchar(max) NULL,
        logs       nvarchar(max) NULL,
        cost_ms    int           NULL,
        started_at datetime2     NOT NULL CONSTRAINT DF_stage_started DEFAULT SYSUTCDATETIME(),
        ended_at   datetime2     NULL,
        CONSTRAINT PK_run_stage PRIMARY KEY (run_id, stage),
        CONSTRAINT FK_stage_run FOREIGN KEY (run_id) REFERENCES nexus.run(run_id) ON DELETE CASCADE
    );
END;
GO

IF OBJECT_ID('nexus.run_node','U') IS NULL
BEGIN
    CREATE TABLE nexus.run_node (
        run_id     nvarchar(64)  NOT NULL,
        node_id    nvarchar(64)  NOT NULL,   -- SQG 算子 id（op1/op2…）
        [state]    nvarchar(20)  NOT NULL CONSTRAINT DF_node_state DEFAULT 'running',
        resolver   nvarchar(100) NULL,       -- 绑定的物理算子
        [call]     nvarchar(max) NULL,       -- 实际调用参数
        [output]   nvarchar(max) NULL,       -- 回填：命中数 / fullname 列表
        [value]    nvarchar(max) NULL,
        [source]   nvarchar(50)  NULL,
        trust      float         NULL,
        error      nvarchar(max) NULL,
        logs       nvarchar(max) NULL,
        cost_ms    int           NULL,
        started_at datetime2     NOT NULL CONSTRAINT DF_node_started DEFAULT SYSUTCDATETIME(),
        ended_at   datetime2     NULL,
        CONSTRAINT PK_run_node PRIMARY KEY (run_id, node_id),
        CONSTRAINT FK_node_run FOREIGN KEY (run_id) REFERENCES nexus.run(run_id) ON DELETE CASCADE
    );
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
