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
        CONSTRAINT PK_collection_store PRIMARY KEY (collection_id, store_id)
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

-- ===== 检索运行（Part 2 预留，结构对称，字段贴检索）=====
IF OBJECT_ID('nexus.query_run','U') IS NULL
BEGIN
    CREATE TABLE nexus.query_run (
        run_id       nvarchar(64)  NOT NULL CONSTRAINT PK_query_run PRIMARY KEY,
        as_user      nvarchar(256) NULL,
        question     nvarchar(max) NULL,
        answer       nvarchar(max) NULL,
        collection   nvarchar(64)  NULL,          -- 检索作用域
        [state]      nvarchar(20)  NOT NULL CONSTRAINT DF_qrun_state DEFAULT 'running',
        node_count   int           NOT NULL CONSTRAINT DF_qrun_node  DEFAULT 0,
        tokens       nvarchar(1000) NULL,         -- JSON 聚合
        dag          nvarchar(max) NULL,          -- SQG/算子图 DAG JSON
        error        nvarchar(max) NULL,
        cost_ms      int           NOT NULL CONSTRAINT DF_qrun_cost  DEFAULT 0,
        created_at   datetime2     NOT NULL CONSTRAINT DF_qrun_created DEFAULT SYSUTCDATETIME(),
        updated_at   datetime2     NOT NULL CONSTRAINT DF_qrun_updated DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_query_run_user ON nexus.query_run(as_user, created_at);
END;
GO

-- 检索 DAG 节点运行态（比 index_node 多 source/trust/input，做出处与可信度）
IF OBJECT_ID('nexus.query_node','U') IS NULL
BEGIN
    CREATE TABLE nexus.query_node (
        run_id      nvarchar(64)  NOT NULL,
        node_id     nvarchar(120) NOT NULL,
        [state]     nvarchar(20)  NOT NULL CONSTRAINT DF_qnode_state DEFAULT 'running',
        [source]    nvarchar(50)  NULL,          -- 产物来源/算子
        trust       float         NULL,          -- 可信度
        [input]     nvarchar(max) NULL,          -- 算子入参（数据，非 token）
        [output]    nvarchar(max) NULL,
        [value]     nvarchar(max) NULL,
        tokens      nvarchar(400) NULL,          -- JSON 本节点明细
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
