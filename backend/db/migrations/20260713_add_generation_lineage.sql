SET XACT_ABORT ON;
GO

IF COL_LENGTH('nexus.index_generation', 'base_generation_id') IS NULL
BEGIN
    ALTER TABLE nexus.index_generation
        ADD base_generation_id nvarchar(64) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID('nexus.index_generation')
      AND name = 'IX_generation_base'
)
BEGIN
    CREATE INDEX IX_generation_base
        ON nexus.index_generation(store_id, base_generation_id, created_at DESC);
END;
GO
