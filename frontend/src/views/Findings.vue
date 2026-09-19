<template>
  <div>
    <el-card shadow="never" class="card-row">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <el-input v-model="q" placeholder="搜索预览/类型/厂商" style="width:200px" clearable @keyup.enter="load" />
        <el-select v-model="filters.review" placeholder="复核状态" style="width:130px" clearable>
          <el-option v-for="(v, k) in { pending: '待处理', confirmed: '已确认', false_positive: '误报', ignored: '已忽略' }" :key="k" :label="v" :value="k" />
        </el-select>
        <el-select v-model="filters.verify" placeholder="验证状态" style="width:140px" clearable>
          <el-option v-for="(v, k) in { not_requested: '未验证', valid: '有效', invalid: '无效', inconclusive: '无法判断', missing_context: '缺少配对信息', unsupported: '不支持验证', rate_limited: '受限流', queued: '排队中', running: '执行中' }" :key="k" :label="v" :value="k" />
        </el-select>
        <el-input v-model="filters.type" placeholder="凭据类型，如 github_pat" style="width:180px" clearable />
        <el-button type="primary" @click="load">查询</el-button>
        <el-divider direction="vertical" />
        <el-button :disabled="!selection.length" @click="batch('confirm')">批量确认</el-button>
        <el-button :disabled="!selection.length" @click="batch('false_positive')">批量误报</el-button>
        <el-button :disabled="!selection.length" @click="batchVerify()">批量验证</el-button>
        <el-divider direction="vertical" />
        <el-button @click="exportData('csv')">导出 CSV（脱敏）</el-button>
        <el-button @click="exportData('csv', false)">CSV（原文）</el-button>
        <el-button @click="exportData('json')">导出 JSON</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="items" size="small" @selection-change="(s: any[]) => selection = s" @row-click="openDetail">
        <el-table-column type="selection" width="42" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="preview" label="凭据（脱敏）" min-width="170">
          <template #default="{ row }"><span style="font-family:monospace">{{ row.preview }}</span></template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="170" />
        <el-table-column prop="vendor" label="厂商" width="100" />
        <el-table-column prop="confidence" label="置信度" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.confidence >= 80 ? 'danger' : row.confidence >= 50 ? 'warning' : 'info'">{{ row.confidence }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复核" width="90">
          <template #default="{ row }">{{ reviewLabel(row.review_status) }}</template>
        </el-table-column>
        <el-table-column label="验证" width="110">
          <template #default="{ row }">{{ verifyLabel(row.verification_status) }}</template>
        </el-table-column>
        <el-table-column prop="occurrence_count" label="位置数" width="75" />
        <el-table-column label="最近发现" width="170">
          <template #default="{ row }">{{ fmtTime(row.last_seen_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click.stop="verifyOne(row)">验证</el-button>
            <el-button size="small" link @click.stop="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination style="margin-top:12px" layout="total, prev, pager, next" :total="total"
                     :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </el-card>

    <el-drawer v-model="detailVisible" :title="`凭据 #${detail?.id} 详情`" size="60%">
      <template v-if="detail">
        <el-descriptions :column="3" border size="small" class="card-row">
          <el-descriptions-item label="类型">{{ detail.type }}</el-descriptions-item>
          <el-descriptions-item label="厂商">{{ detail.vendor || '—' }}</el-descriptions-item>
          <el-descriptions-item label="置信度">{{ detail.confidence }}</el-descriptions-item>
          <el-descriptions-item label="规则">{{ detail.rule_id }}</el-descriptions-item>
          <el-descriptions-item label="首次发现">{{ fmtTime(detail.first_seen_at) }}</el-descriptions-item>
          <el-descriptions-item label="最近发现">{{ fmtTime(detail.last_seen_at) }}</el-descriptions-item>
        </el-descriptions>
        <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
          <el-button size="small" type="success" @click="reviewOne('confirm')">确认真实</el-button>
          <el-button size="small" type="warning" @click="reviewOne('false_positive')">标记误报</el-button>
          <el-button size="small" @click="reviewOne('ignore')">忽略</el-button>
          <el-button size="small" @click="reviewOne('restore')">恢复待处理</el-button>
          <el-button size="small" type="primary" @click="reveal">显示原文（留审计）</el-button>
        </div>
        <el-card shadow="never" :header="`出现位置（${detail.locations.length}）`" class="card-row">
          <div v-for="loc in detail.locations" :key="loc.id" style="border-bottom:1px dashed #eee;padding:8px 0">
            <div><b>{{ loc.platform }}</b> · {{ loc.path }}<span v-if="loc.line_start"> :{{ loc.line_start }}</span></div>
            <div style="color:#5a90d0;font-size:12px;word-break:break-all">{{ loc.origin_url || '本地内容' }}</div>
            <div style="font-size:12px;color:#8a94a2">版本 {{ loc.version_kind }}:{{ (loc.version_id || '').slice(0, 16) }} · 首次 {{ fmtTime(loc.first_seen_at) }} · 最近 {{ fmtTime(loc.last_seen_at) }}</div>
            <pre style="background:#f7f8fa;padding:8px;font-size:12px;overflow:auto;max-height:120px;margin:6px 0 0">{{ loc.context_masked }}</pre>
          </div>
        </el-card>
        <el-card shadow="never" :header="`验证历史（${detail.verification_history.length}）`" class="card-row">
          <el-table :data="detail.verification_history" size="small" v-if="detail.verification_history.length">
            <el-table-column prop="verifier_id" label="验证器" width="120" />
            <el-table-column label="结果" width="110"><template #default="{ row }">{{ verifyLabel(row.status) }}</template></el-table-column>
            <el-table-column label="证据"><template #default="{ row }">{{ JSON.stringify(row.evidence) }}</template></el-table-column>
            <el-table-column label="时间" width="170"><template #default="{ row }">{{ fmtTime(row.created_at) }}</template></el-table-column>
          </el-table>
          <el-empty v-else description="尚未验证（默认关闭）" :image-size="50" />
        </el-card>
        <el-card shadow="never" :header="`复核与审计记录（${detail.review_logs.length}）`">
          <div v-for="(l, i) in detail.review_logs" :key="i" style="font-size:12px;padding:3px 0">
            {{ fmtTime(l.created_at) }} · {{ l.actor }} · {{ l.action }} <span v-if="l.note">· {{ l.note }}</span>
          </div>
          <el-empty v-if="!detail.review_logs.length" description="无记录" :image-size="40" />
        </el-card>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import http, { fmtTime, STATUS_LABELS } from '../api'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const q = ref('')
const filters = ref<any>({ review: '', verify: '', type: '' })
const selection = ref<any[]>([])
const detail = ref<any>(null)
const detailVisible = ref(false)

const reviewLabel = (s: string) => ({ pending: '待处理', confirmed: '已确认', false_positive: '误报', ignored: '已忽略' } as any)[s] || s
const verifyLabel = (s: string) => STATUS_LABELS[s] || s

const load = async () => {
  const resp = await http.get('/findings', { params: {
    q: q.value || undefined, review: filters.value.review || undefined,
    verify: filters.value.verify || undefined, type: filters.value.type || undefined,
    page: page.value, page_size: pageSize,
  } })
  items.value = resp.data.items
  total.value = resp.data.total
}
onMounted(load)

const openDetail = async (row: any) => {
  detail.value = (await http.get(`/findings/${row.id}`)).data
  detailVisible.value = true
}

const reviewOne = async (action: string) => {
  await http.post(`/findings/${detail.value.id}/review`, { action, note: null })
  ElMessage.success('已更新')
  detail.value = (await http.get(`/findings/${detail.value.id}`)).data
  load()
}

const verifyOne = async (row: any) => {
  const resp = await http.post(`/findings/${row.id}/verify`)
  ElMessage[resp.data.queued ? 'success' : 'warning'](resp.data.queued ? '已加入验证队列' : `该类型${STATUS_LABELS[resp.data.status] || resp.data.status}`)
  load()
}

const batch = async (action: string) => {
  await http.post('/findings/batch-review', { ids: selection.value.map((s) => s.id), action })
  ElMessage.success('批量处理完成')
  load()
}

const batchVerify = async () => {
  const resp = await http.post('/findings/batch-verify', { ids: selection.value.map((s) => s.id) })
  ElMessage.success(`已入队 ${resp.data.queued} 条，不支持验证 ${resp.data.unsupported} 条`)
  load()
}

const reveal = async () => {
  const resp = await http.post(`/findings/${detail.value.id}/reveal`)
  ElMessageBox_alert(resp.data.secret)
}
const ElMessageBox_alert = (secret: string) => {
  import('element-plus').then(({ ElMessageBox }) =>
    ElMessageBox.alert(`<span style="font-family:monospace;word-break:break-all">${secret}</span>`, '凭据原文（已记录审计）', { dangerouslyUseHTMLString: true }))
}

const exportData = (fmt: string, masked: boolean = true) => {
  const params = new URLSearchParams({ masked: String(masked) })
  if (filters.value.type) params.set('type', filters.value.type)
  if (filters.value.review) params.set('review', filters.value.review)
  window.open(`/api/export/findings.${fmt}?${params.toString()}`)
}
</script>
