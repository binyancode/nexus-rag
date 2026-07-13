using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Data;
using Microsoft.Data.SqlClient;
using NexusRAG.Server.Models;
using NexusRAG.Server.Services;

namespace NexusRAG.Server.Controllers
{
    // 索引运行进度：BFF 直连 DB 读 nexus.index_run（含 DAG 结构 JSON）+ nexus.index_node（节点运行态）。
    // 纯非敏感 DB 读，归 BFF。启动/取消索引走 Python（需 Key Vault + workflow 进程内的取消令牌）。
    [Authorize]
    [ApiController]
    [Route("api/index-runs")]
    public class IndexRunsController : ControllerBase
    {
        private readonly SqlService _sql;

        public IndexRunsController(SqlService sql)
        {
            _sql = sql;
        }

        // 运行历史：最近的索引运行列表（关窗后回来还能看到进度/结果）。不含 dag 大字段，列表轻量。
        [HttpGet("")]
        public async Task<APIResponseModel> ListRuns([FromQuery] int top = 100)
        {
            if (top <= 0 || top > 500) top = 100;
            var table = await _sql.QueryAsync(
                @"SELECT TOP (@top) run_id, generation_id, as_user, category, store_id, [state],
                         document_count AS doc_count, block_count, node_count, tokens,
                         cost_ms, error, created_at, updated_at
                  FROM nexus.index_run
                  ORDER BY created_at DESC",
                new[] { new SqlParameter("@top", top) });

            var runs = table.AsEnumerable().Select(r => new
            {
                run_id = r.Field<string?>("run_id"),
                generation_id = r.Field<string?>("generation_id"),
                as_user = r.Field<string?>("as_user"),
                category = r.Field<string?>("category"),
                store_id = r.Field<string?>("store_id"),
                state = r.Field<string?>("state"),
                doc_count = r.IsNull("doc_count") ? 0 : r.Field<int>("doc_count"),
                block_count = r.IsNull("block_count") ? 0 : r.Field<int>("block_count"),
                node_count = r.IsNull("node_count") ? 0 : r.Field<int>("node_count"),
                tokens = r.Field<string?>("tokens"),   // JSON 字符串
                cost_ms = r.IsNull("cost_ms") ? 0 : r.Field<int>("cost_ms"),
                error = r.Field<string?>("error"),
                created_at = r.Field<DateTime?>("created_at"),
                updated_at = r.Field<DateTime?>("updated_at"),
            }).ToList();

            return new APIResponseModel { Data = new { runs } };
        }

        // 单次索引运行：run 总体（含 dag/tokens 原始 JSON 字符串，前端解析）+ 全部节点运行态
        [HttpGet("{runId}")]
        public async Task<APIResponseModel> GetRun(string runId)
        {
            var runTable = await _sql.QueryAsync(
                @"SELECT run_id, generation_id, as_user, store_id, category, max_parallel, [state],
                         current_phase, document_count AS doc_count, block_count, entity_count,
                         action_count, assertion_count, graph_edge_count, quality_issue_count,
                         node_count, tokens, dag, error, cost_ms, created_at, updated_at
                  FROM nexus.index_run WHERE run_id = @runId",
                new[] { new SqlParameter("@runId", runId) });

            if (runTable.Rows.Count == 0)
            {
                return new APIResponseModel { State = "error", Message = $"index run 不存在: {runId}" };
            }

            var r = runTable.Rows[0];
            var run = new
            {
                run_id = r.Field<string?>("run_id"),
                generation_id = r.Field<string?>("generation_id"),
                as_user = r.Field<string?>("as_user"),
                store_id = r.Field<string?>("store_id"),
                category = r.Field<string?>("category"),
                max_parallel = r.IsNull("max_parallel") ? 8 : r.Field<int>("max_parallel"),
                state = r.Field<string?>("state"),
                current_phase = r.Field<string?>("current_phase"),
                doc_count = r.IsNull("doc_count") ? 0 : r.Field<int>("doc_count"),
                block_count = r.IsNull("block_count") ? 0 : r.Field<int>("block_count"),
                entity_count = r.IsNull("entity_count") ? 0 : r.Field<int>("entity_count"),
                action_count = r.IsNull("action_count") ? 0 : r.Field<int>("action_count"),
                assertion_count = r.IsNull("assertion_count") ? 0 : r.Field<int>("assertion_count"),
                graph_edge_count = r.IsNull("graph_edge_count") ? 0 : r.Field<int>("graph_edge_count"),
                quality_issue_count = r.IsNull("quality_issue_count") ? 0 : r.Field<int>("quality_issue_count"),
                node_count = r.IsNull("node_count") ? 0 : r.Field<int>("node_count"),
                tokens = r.Field<string?>("tokens"),   // JSON 字符串
                dag = r.Field<string?>("dag"),          // JSON 字符串
                error = r.Field<string?>("error"),
                cost_ms = r.IsNull("cost_ms") ? 0 : r.Field<int>("cost_ms"),
                created_at = r.Field<DateTime?>("created_at"),
                updated_at = r.Field<DateTime?>("updated_at"),
            };

            var nodeTable = await _sql.QueryAsync(
                @"SELECT node_id, [state], op, [input], [output], [value], tokens,
                         error, cost_ms, started_at, ended_at
                  FROM nexus.index_node WHERE run_id = @runId",
                new[] { new SqlParameter("@runId", runId) });

            var nodes = nodeTable.AsEnumerable().Select(n => new
            {
                node_id = n.Field<string?>("node_id"),
                state = n.Field<string?>("state"),
                op = n.Field<string?>("op"),
                input = n.Field<string?>("input"),
                tokens = n.Field<string?>("tokens"),
                // Keep the established frontend shape: display text comes from value.
                // Fall back to JSON output for compatibility with older rows.
                output = n.Field<string?>("value") ?? n.Field<string?>("output"),
                value = n.Field<string?>("value"),
                output_json = n.Field<string?>("output"),
                error = n.Field<string?>("error"),
                cost_ms = n.IsNull("cost_ms") ? (int?)null : n.Field<int>("cost_ms"),
                started_at = n.Field<DateTime?>("started_at"),
                ended_at = n.Field<DateTime?>("ended_at"),
            }).ToList();

            return new APIResponseModel { Data = new { run, nodes } };
        }
    }
}
