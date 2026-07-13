<template>
  <div class="collections-page">
    <div class="cp-head">
      <div><h1>Collection 管理</h1><p>管理查询可见范围、AI Search Store 成员和用户授权。</p></div>
      <el-button type="primary" @click="openCreate">＋ 新增 Collection</el-button>
    </div>

    <el-table v-loading="loading" :data="data.collections" empty-text="暂无 Collection">
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="collection_id" label="ID" min-width="140" />
      <el-table-column label="可见性" width="110">
        <template #default="{ row }"><el-tag :type="row.is_public ? 'success' : 'info'">{{ row.is_public ? '公开' : '授权可见' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="Store" width="90"><template #default="{ row }">{{ row.store_count }}</template></el-table-column>
      <el-table-column label="授权" width="90"><template #default="{ row }">{{ row.access_count }}</template></el-table-column>
      <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="editing ? '编辑 Collection' : '新增 Collection'" width="720px" @closed="reset">
      <el-tabs v-model="tab">
        <el-tab-pane label="基本信息" name="base">
          <div class="field"><label>Collection ID *</label><el-input v-model="form.collection_id" :disabled="editing" placeholder="如 drug-regulations" /></div>
          <div class="field"><label>名称 *</label><el-input v-model="form.name" /></div>
          <div class="field"><label>说明</label><el-input v-model="form.description" type="textarea" :rows="3" /></div>
          <div class="field row"><label>公开 Collection</label><el-switch v-model="form.is_public" /><span>所有登录用户可见；关闭后仅授权用户/角色可见。</span></div>
        </el-tab-pane>

        <el-tab-pane :label="`成员 Store（${form.store_ids.length}）`" name="stores">
          <el-checkbox-group v-model="form.store_ids" class="store-list">
            <el-checkbox v-for="s in data.stores" :key="s.store_id" :value="s.store_id" class="store-item">
              <span class="store-name">{{ s.name }}</span>
              <small>{{ s.store_id }} · {{ s.index_name || '未指定索引' }}</small>
            </el-checkbox>
          </el-checkbox-group>
          <div v-if="!data.stores.length" class="empty">暂无已注册的 AI Search Store</div>
        </el-tab-pane>

        <el-tab-pane :label="`访问授权（${form.access.length}）`" name="access">
          <div class="access-help">私有 Collection 必须配置用户授权。勾选“默认”时，会自动取消该用户在其他 Collection 上的默认项。</div>
          <div v-for="(a, i) in form.access" :key="i" class="access-row">
            <el-tag type="info" style="width:64px;justify-content:center">用户</el-tag>
            <el-input v-model="a.principal_id" placeholder="用户账号或角色 ID" />
            <el-checkbox v-model="a.is_default">默认</el-checkbox>
            <el-button link type="danger" @click="form.access.splice(i,1)">删除</el-button>
          </div>
          <el-button plain @click="form.access.push({ principal_type:'user', principal_id:'', is_default:false })">＋ 添加授权</el-button>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="dialog=false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!canSave" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createCollection, deleteCollection, listCollectionsAdmin, updateCollection,
  type CollectionAdminData, type CollectionItem, type CollectionSavePayload,
} from '../bff/Collections.js'

const emptyData = (): CollectionAdminData => ({ collections:[], stores:[], members:[], access:[] })
const data = reactive<CollectionAdminData>(emptyData())
const loading = ref(false), saving = ref(false), dialog = ref(false), editing = ref(false), tab = ref('base')
const form = reactive<CollectionSavePayload>({ collection_id:'', name:'', description:'', is_public:false, store_ids:[], access:[] })
const canSave = computed(() => !!form.collection_id.trim() && !!form.name.trim()
  && form.store_ids.length > 0
  && (form.is_public || form.access.some(a => a.principal_id.trim())))

onMounted(load)
async function load() {
  loading.value=true
  try { Object.assign(data, await listCollectionsAdmin()) }
  catch { ElMessage.error('加载 Collection 失败') }
  finally { loading.value=false }
}
function openCreate() { reset(); editing.value=false; dialog.value=true }
function openEdit(row: CollectionItem) {
  reset(); editing.value=true
  form.collection_id=row.collection_id; form.name=row.name; form.description=row.description || ''; form.is_public=row.is_public
  form.store_ids=data.members.filter(x=>x.collection_id===row.collection_id).map(x=>x.store_id)
  form.access=data.access.filter(x=>x.collection_id===row.collection_id).map(x=>({ principal_type:x.principal_type, principal_id:x.principal_id, is_default:x.is_default }))
  dialog.value=true
}
function reset() {
  tab.value='base'; form.collection_id=''; form.name=''; form.description=''; form.is_public=false
  form.store_ids=[]; form.access=[]
}
async function save() {
  saving.value=true
  try {
    const payload: CollectionSavePayload = {
      collection_id:form.collection_id.trim(), name:form.name.trim(), description:form.description?.trim() || null,
      is_public:form.is_public, store_ids:[...new Set(form.store_ids)],
      access:form.access.filter(a=>a.principal_id.trim()).map(a=>({ ...a, principal_id:a.principal_id.trim() })),
    }
    if (editing.value) await updateCollection(payload.collection_id,payload); else await createCollection(payload)
    ElMessage.success('Collection 已保存'); dialog.value=false; await load()
  } catch { /* 拦截器已提示 */ }
  finally { saving.value=false }
}
async function remove(row: CollectionItem) {
  try {
    await ElMessageBox.confirm(`删除 Collection“${row.name}”？只删除范围配置，不删除 Store 或索引数据。`,'删除 Collection',{type:'warning',confirmButtonText:'删除',cancelButtonText:'取消'})
    await deleteCollection(row.collection_id); ElMessage.success('Collection 已删除'); await load()
  } catch { /* 取消或拦截器已提示 */ }
}
</script>

<style scoped>
.collections-page { flex:1; min-height:0; overflow:auto; padding:24px 28px; }
.cp-head { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:16px; }
.cp-head h1 { margin:0 0 4px; font-size:20px; }
.cp-head p { margin:0; color:var(--beone-text-secondary); font-size:13px; }
.field { margin-bottom:14px; }
.field > label { display:block; margin-bottom:6px; color:var(--beone-text-secondary); font-size:12px; font-weight:600; }
.field.row { display:flex; align-items:center; gap:10px; }
.field.row > label { margin:0; }
.field.row > span { color:var(--beone-text-secondary); font-size:11px; }
.store-list { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.store-item { height:auto; margin:0!important; padding:10px; border:1px solid var(--beone-border); border-radius:7px; }
.store-item :deep(.el-checkbox__label) { display:flex; min-width:0; flex-direction:column; }
.store-name { font-size:12px; font-weight:600; }
.store-item small { color:var(--beone-text-secondary); overflow:hidden; text-overflow:ellipsis; }
.access-help { margin-bottom:10px; color:var(--beone-text-secondary); font-size:11px; }
.access-row { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.empty { padding:28px; text-align:center; color:var(--beone-text-secondary); }
</style>
