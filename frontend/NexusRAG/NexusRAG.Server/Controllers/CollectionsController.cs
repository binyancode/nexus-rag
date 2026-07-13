using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.SqlClient;
using NexusRAG.Server.Models;
using NexusRAG.Server.Services;
using System.Data;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace NexusRAG.Server.Controllers
{
    [Authorize]
    [ApiController]
    [Route("api/collections")]
    public class CollectionsController : ControllerBase
    {
        private readonly SqlService _sql;
        public CollectionsController(SqlService sql) { _sql = sql; }

        [HttpGet]
        public async Task<APIResponseModel> List()
        {
            if (!await IsAdmin()) return Denied();
            var collections = await _sql.QueryAsync(
                @"SELECT c.collection_id,c.name,c.description,c.is_public,
                         COUNT(DISTINCT cs.store_id) AS store_count,
                         COUNT(DISTINCT CONCAT(ca.principal_type,':',ca.principal_id)) AS access_count
                  FROM nexus.collection c
                  LEFT JOIN nexus.collection_store cs ON cs.collection_id=c.collection_id
                  LEFT JOIN nexus.collection_access ca ON ca.collection_id=c.collection_id
                  GROUP BY c.collection_id,c.name,c.description,c.is_public
                  ORDER BY c.name");
            var stores = await _sql.QueryAsync(
                @"SELECT store_id,name,credential_name,index_name,kind,is_default
                  FROM nexus.search_store ORDER BY name");
            var members = await _sql.QueryAsync(
                "SELECT collection_id,store_id FROM nexus.collection_store ORDER BY collection_id,store_id");
            var access = await _sql.QueryAsync(
                @"SELECT collection_id,principal_type,principal_id,is_default
                  FROM nexus.collection_access ORDER BY collection_id,principal_type,principal_id");

            return new APIResponseModel { Data = new {
                collections = collections.AsEnumerable().Select(r => new {
                    collection_id=r.Field<string>("collection_id"), name=r.Field<string>("name"),
                    description=r.Field<string?>("description"), is_public=r.Field<bool>("is_public"),
                    store_count=Convert.ToInt32(r["store_count"]), access_count=Convert.ToInt32(r["access_count"]),
                }),
                stores = stores.AsEnumerable().Select(r => new {
                    store_id=r.Field<string>("store_id"), name=r.Field<string>("name"),
                    credential_name=r.Field<string>("credential_name"), index_name=r.Field<string?>("index_name"),
                    kind=r.Field<string>("kind"), is_default=r.Field<bool>("is_default"),
                }),
                members = members.AsEnumerable().Select(r => new {
                    collection_id=r.Field<string>("collection_id"), store_id=r.Field<string>("store_id"),
                }),
                access = access.AsEnumerable().Select(r => new {
                    collection_id=r.Field<string>("collection_id"), principal_type=r.Field<string>("principal_type"),
                    principal_id=r.Field<string>("principal_id"), is_default=r.Field<bool>("is_default"),
                }),
            }};
        }

        [HttpPost]
        public async Task<APIResponseModel> Create([FromBody] CollectionSaveRequest body)
        {
            if (!await IsAdmin()) return Denied();
            return await Save(body, create: true);
        }

        [HttpPut("{collectionId}")]
        public async Task<APIResponseModel> Update(string collectionId, [FromBody] CollectionSaveRequest body)
        {
            if (!await IsAdmin()) return Denied();
            if (!string.Equals(collectionId, body.CollectionId, StringComparison.Ordinal))
                return new APIResponseModel { State="error", Message="URL 与 body 的 collection_id 不一致" };
            return await Save(body, create: false);
        }

        [HttpDelete("{collectionId}")]
        public async Task<APIResponseModel> Delete(string collectionId)
        {
            if (!await IsAdmin()) return Denied();
            await _sql.ExecuteNonQueryAsync(
                @"SET XACT_ABORT ON; BEGIN TRANSACTION;
                  DELETE FROM nexus.collection_access WHERE collection_id=@id;
                  DELETE FROM nexus.collection_store WHERE collection_id=@id;
                  DELETE FROM nexus.collection WHERE collection_id=@id;
                  COMMIT TRANSACTION;",
                new[] { new SqlParameter("@id", collectionId) });
            return new APIResponseModel { Data = new { collection_id=collectionId } };
        }

        private async Task<APIResponseModel> Save(CollectionSaveRequest body, bool create)
        {
            var id=(body.CollectionId ?? "").Trim();
            var name=(body.Name ?? "").Trim();
            if (string.IsNullOrEmpty(id) || string.IsNullOrEmpty(name))
                return new APIResponseModel { State="error", Message="collection_id / name 必填" };
            if (body.StoreIds.Count == 0)
                return new APIResponseModel { State="error", Message="Collection 至少需要一个 Store" };
            if (!body.IsPublic && !body.Access.Any(x => !string.IsNullOrWhiteSpace(x.PrincipalId)))
                return new APIResponseModel { State="error", Message="私有 Collection 至少需要一个用户授权" };
            if (body.Access.Any(x => x.PrincipalType != "user"))
                return new APIResponseModel { State="error", Message="当前版本仅支持用户授权；角色授权待角色声明接入后开放" };
            if (body.Access.Any(x => string.IsNullOrWhiteSpace(x.PrincipalId)))
                return new APIResponseModel { State="error", Message="授权用户不能为空" };
            if (body.Access.GroupBy(x => new { x.PrincipalType, x.PrincipalId })
                    .Any(g => g.Count() > 1))
                return new APIResponseModel { State="error", Message="同一主体不能重复授权" };
            var storeJson=JsonSerializer.Serialize(body.StoreIds.Distinct());
            var accessJson=JsonSerializer.Serialize(body.Access.Select(x => new {
                principal_type=x.PrincipalType, principal_id=x.PrincipalId.Trim(), is_default=x.IsDefault,
            }));
            var sql = create
                ? @"SET XACT_ABORT ON; BEGIN TRANSACTION;
                    IF EXISTS(SELECT 1 FROM nexus.collection WHERE collection_id=@id) THROW 51000,'Collection 已存在',1;
                                        IF EXISTS(SELECT 1 FROM OPENJSON(@stores) x LEFT JOIN nexus.search_store s ON s.store_id=x.[value] WHERE s.store_id IS NULL)
                                            THROW 51002,'包含不存在的 Store',1;
                    INSERT nexus.collection(collection_id,name,description,is_public) VALUES(@id,@name,@description,@public);
                    INSERT nexus.collection_store(collection_id,store_id)
                      SELECT @id,[value] FROM OPENJSON(@stores);
                                        UPDATE old SET is_default=0
                                            FROM nexus.collection_access old
                                            JOIN OPENJSON(@access) WITH(principal_type nvarchar(20),principal_id nvarchar(256),is_default bit) incoming
                                                ON incoming.principal_type=old.principal_type AND incoming.principal_id=old.principal_id
                                            WHERE incoming.is_default=1;
                    INSERT nexus.collection_access(collection_id,principal_type,principal_id,is_default)
                      SELECT @id,principal_type,principal_id,is_default
                      FROM OPENJSON(@access) WITH(principal_type nvarchar(20),principal_id nvarchar(256),is_default bit);
                    COMMIT TRANSACTION;"
                : @"SET XACT_ABORT ON; BEGIN TRANSACTION;
                    UPDATE nexus.collection SET name=@name,description=@description,is_public=@public,
                           updated_at=SYSUTCDATETIME() WHERE collection_id=@id;
                    IF @@ROWCOUNT=0 THROW 51001,'Collection 不存在',1;
                                        IF EXISTS(SELECT 1 FROM OPENJSON(@stores) x LEFT JOIN nexus.search_store s ON s.store_id=x.[value] WHERE s.store_id IS NULL)
                                            THROW 51002,'包含不存在的 Store',1;
                    DELETE nexus.collection_store WHERE collection_id=@id;
                    INSERT nexus.collection_store(collection_id,store_id)
                      SELECT @id,[value] FROM OPENJSON(@stores);
                    DELETE nexus.collection_access WHERE collection_id=@id;
                                        UPDATE old SET is_default=0
                                            FROM nexus.collection_access old
                                            JOIN OPENJSON(@access) WITH(principal_type nvarchar(20),principal_id nvarchar(256),is_default bit) incoming
                                                ON incoming.principal_type=old.principal_type AND incoming.principal_id=old.principal_id
                                            WHERE incoming.is_default=1;
                    INSERT nexus.collection_access(collection_id,principal_type,principal_id,is_default)
                      SELECT @id,principal_type,principal_id,is_default
                      FROM OPENJSON(@access) WITH(principal_type nvarchar(20),principal_id nvarchar(256),is_default bit);
                    COMMIT TRANSACTION;";
            await _sql.ExecuteNonQueryAsync(sql, new[] {
                new SqlParameter("@id",id), new SqlParameter("@name",name),
                new SqlParameter("@description",(object?)body.Description ?? DBNull.Value),
                new SqlParameter("@public",body.IsPublic), new SqlParameter("@stores",storeJson),
                new SqlParameter("@access",accessJson),
            });
            return new APIResponseModel { Data = new { collection_id=id } };
        }

        private async Task<bool> IsAdmin()
        {
            var userName=User.Identity?.Name;
            if (string.IsNullOrEmpty(userName)) return false;
            var value=await _sql.ExecuteScalarAsync(
                "SELECT TOP 1 is_admin FROM nexus.app_user WHERE user_name=@user",
                new[] { new SqlParameter("@user",userName) });
            return value != null && value != DBNull.Value && Convert.ToBoolean(value);
        }

        private static APIResponseModel Denied() =>
            new() { State="error", Message="仅管理员可管理 Collection" };
    }

    public class CollectionSaveRequest
    {
        [JsonPropertyName("collection_id")] public string? CollectionId { get; set; }
        [JsonPropertyName("name")] public string? Name { get; set; }
        [JsonPropertyName("description")] public string? Description { get; set; }
        [JsonPropertyName("is_public")] public bool IsPublic { get; set; }
        [JsonPropertyName("store_ids")] public List<string> StoreIds { get; set; } = new();
        [JsonPropertyName("access")] public List<CollectionAccessRequest> Access { get; set; } = new();
    }

    public class CollectionAccessRequest
    {
        [JsonPropertyName("principal_type")] public string PrincipalType { get; set; } = "user";
        [JsonPropertyName("principal_id")] public string PrincipalId { get; set; } = "";
        [JsonPropertyName("is_default")] public bool IsDefault { get; set; }
    }
}
