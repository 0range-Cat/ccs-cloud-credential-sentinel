<template>
  <div>
    <el-row :gutter="14" class="card-row">
      <el-col :span="4" v-for="c in cards" :key="c.label">
        <el-card shadow="never"><div class="stat-num">{{ c.value }}</div><div class="stat-label">{{ c.label }}</div></el-card>
      </el-col>
    </el-row>
    <el-row :gutter="14" class="card-row">
      <el-col :span="8">
        <el-card shadow="never" header="按平台分布（出现位置）">
          <el-table :data="stats.by_platform || []" size="small">
            <el-table-column prop="0" label="平台" />
            <el-table-column prop="1" label="位置数" width="100" />
          </el-table>
          <el-empty v-if="!(stats.by_platform || []).length" description="暂无数据" :image-size="50" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="凭据类型 Top 20（去重后）">
          <el-table :data="stats.by_type_top || []" size="small" max-height="320">
            <el-table-column prop="0" label="类型" />
            <el-table-column prop="1" label="数量" width="80" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="发现时延（泄露公开 → 系统发现）">
          <div class="stat-num">{{ latency.p50_seconds === null ? '—' : fmtSeconds(latency.p50_seconds) }}</div>
          <div class="stat-label">P50（样本数 {{ latency.sample_count ?? 0 }}）</div>
          <div class="stat-num" style="margin-top:10px">{{ latency.p95_seconds === null ? '—' : fmtSeconds(latency.p95_seconds) }}</div>
          <div class="stat-label">P95</div>
          <el-alert :title="latency.note || ''" type="info" :closable="false" style="margin-top:12px" />
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" header="最近扫描批次">
      <el-table :data="stats.recent_runs || []" size="small">
        <el-table-column prop="id" label="批次" width="70" />
        <el-table-column prop="task_id" label="任务" width="70" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ STATUS_LABELS[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column label="触发" width="90">
          <template #default="{ row }">{{ row.trigger === 'manual' ? '手动' : '调度' }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="新凭据 / 新位置 / 候选 / 已见内容">
          <template #default="{ row }">
            {{ (row.stats || {}).new_credentials ?? 0 }} / {{ (row.stats || {}).new_occurrences ?? 0 }} /
            {{ (row.stats || {}).candidates ?? 0 }} / {{ (row.stats || {}).items_seen ?? 0 }}
            <span v-if="(row.stats || {}).stop_reason && (row.stats || {}).stop_reason !== 'completed'"
                  style="color:#e6a23c">（{{ (row.stats || {}).stop_reason }}）</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!(stats.recent_runs || []).length" description="暂无扫描记录，请到“监控任务”创建" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import http, { fmtTime, fmtSeconds, STATUS_LABELS } from '../api'
import { computed, onMounted, ref } from 'vue'

const stats = ref<any>({})
const load = async () => { stats.value = (await http.get('/overview/stats')).data }
onMounted(load)
const latency = computed(() => stats.value.detection_latency || {})

const review = computed(() => stats.value.by_review_status || {})
const verify = computed(() => stats.value.by_verification_status || {})
const cards = computed(() => [
  { label: '去重凭据', value: stats.value.credentials_total ?? 0 },
  { label: '唯一泄露位置', value: stats.value.occurrences_total ?? 0 },
  { label: '待复核候选', value: review.value.pending ?? 0 },
  { label: '验证有效', value: verify.value.valid ?? 0 },
  { label: '验证无效', value: verify.value.invalid ?? 0 },
  { label: '无法判断', value: (verify.value.inconclusive ?? 0) + (verify.value.rate_limited ?? 0) + (verify.value.network_error ?? 0) },
])
</script>
