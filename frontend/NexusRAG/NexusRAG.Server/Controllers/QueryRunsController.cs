using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.SqlClient;
using NexusRAG.Server.Models;
using NexusRAG.Server.Services;
using System.Data;

namespace NexusRAG.Server.Controllers
{
    [Authorize]
    [ApiController]
    [Route("api/query-runs")]
    public class QueryRunsController : ControllerBase
    {
        private readonly SqlService _sql;
        public QueryRunsController(SqlService sql) { _sql = sql; }

        [HttpGet("")]
        public async Task<APIResponseModel> List([FromQuery] int top = 100)
        {
            if (top <= 0 || top > 500) top = 100;
            var table = await _sql.QueryAsync(
                @"SELECT TOP (@top) run_id,as_user,question,answer,collection_id,collection_name,collection_selected_by,
                         [state],node_count,tokens,error,cost_ms,created_at,updated_at
                  FROM nexus.query_run ORDER BY created_at DESC",
                new[] { new SqlParameter("@top", top) });
            var runs = table.AsEnumerable().Select(r => new
            {
                run_id = r.Field<string?>("run_id"),
                as_user = r.Field<string?>("as_user"),
                question = r.Field<string?>("question"),
                answer = r.Field<string?>("answer"),
                collection_id = r.Field<string?>("collection_id"),
                collection_name = r.Field<string?>("collection_name"),
                collection_selected_by = r.Field<string?>("collection_selected_by"),
                state = r.Field<string?>("state"),
                node_count = r.IsNull("node_count") ? 0 : r.Field<int>("node_count"),
                tokens = r.Field<string?>("tokens"),
                error = r.Field<string?>("error"),
                cost_ms = r.IsNull("cost_ms") ? 0 : r.Field<int>("cost_ms"),
                created_at = r.Field<DateTime?>("created_at"),
                updated_at = r.Field<DateTime?>("updated_at"),
            }).ToList();
            return new APIResponseModel { Data = new { runs } };
        }

        [HttpGet("{runId}")]
        public async Task<APIResponseModel> Get(string runId)
        {
            var table = await _sql.QueryAsync(
                @"SELECT run_id,as_user,question,answer,citations,collection_id,collection_name,
                         collection_selected_by,allowed_stores,generation_scope,max_parallel,budgets,
                         [state],current_stage,
                         node_count,tokens,error,cost_ms,created_at,updated_at
                  FROM nexus.query_run WHERE run_id=@runId",
                new[] { new SqlParameter("@runId", runId) });
            if (table.Rows.Count == 0)
                return new APIResponseModel { State = "error", Message = $"query run 不存在: {runId}" };
            var r = table.Rows[0];
            var run = new
            {
                run_id = r.Field<string?>("run_id"), as_user = r.Field<string?>("as_user"),
                question = r.Field<string?>("question"), answer = r.Field<string?>("answer"),
                citations = r.Field<string?>("citations"),
                collection_id = r.Field<string?>("collection_id"),
                collection_name = r.Field<string?>("collection_name"),
                collection_selected_by = r.Field<string?>("collection_selected_by"),
                allowed_stores = r.Field<string?>("allowed_stores"),
                generation_scope = r.Field<string?>("generation_scope"),
                max_parallel = r.IsNull("max_parallel") ? 8 : r.Field<int>("max_parallel"),
                budgets = r.Field<string?>("budgets"),
                state = r.Field<string?>("state"), current_stage = r.Field<string?>("current_stage"),
                node_count = r.IsNull("node_count") ? 0 : r.Field<int>("node_count"),
                tokens = r.Field<string?>("tokens"),
                error = r.Field<string?>("error"),
                cost_ms = r.IsNull("cost_ms") ? 0 : r.Field<int>("cost_ms"),
                created_at = r.Field<DateTime?>("created_at"), updated_at = r.Field<DateTime?>("updated_at"),
            };
            var nodeTable = await _sql.QueryAsync(
                @"SELECT node_id,[state],op,[input],[output],[value],tokens,error,cost_ms,started_at,ended_at
                  FROM nexus.query_node WHERE run_id=@runId",
                new[] { new SqlParameter("@runId", runId) });
            var nodes = nodeTable.AsEnumerable().Select(n => new
            {
                node_id = n.Field<string?>("node_id"), state = n.Field<string?>("state"),
                op = n.Field<string?>("op"),
                input = n.Field<string?>("input"), output = n.Field<string?>("output"), value = n.Field<string?>("value"),
                tokens = n.Field<string?>("tokens"), error = n.Field<string?>("error"),
                cost_ms = n.IsNull("cost_ms") ? (int?)null : n.Field<int>("cost_ms"),
                started_at = n.Field<DateTime?>("started_at"), ended_at = n.Field<DateTime?>("ended_at"),
            }).ToList();
            var stageTable = await _sql.QueryAsync(
                @"SELECT stage_id,ordinal,name,[state],[input],[output],tokens,error,cost_ms,started_at,ended_at
                  FROM nexus.query_stage WHERE run_id=@runId ORDER BY ordinal",
                new[] { new SqlParameter("@runId", runId) });
            var stages = stageTable.AsEnumerable().Select(s => new
            {
                stage_id = s.Field<string?>("stage_id"), ordinal = s.Field<byte>("ordinal"),
                name = s.Field<string?>("name"), state = s.Field<string?>("state"),
                input = s.Field<string?>("input"), output = s.Field<string?>("output"),
                tokens = s.Field<string?>("tokens"), error = s.Field<string?>("error"),
                cost_ms = s.IsNull("cost_ms") ? (int?)null : s.Field<int>("cost_ms"),
                started_at = s.Field<DateTime?>("started_at"), ended_at = s.Field<DateTime?>("ended_at"),
            }).ToList();
            return new APIResponseModel { Data = new { run, stages, nodes } };
        }
    }
}
