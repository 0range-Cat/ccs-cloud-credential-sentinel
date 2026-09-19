<template>
  <div>
    <el-card shadow="never" header="验证器（最小认证原则）" class="card-row">
      <el-alert type="warning" :closable="false" style="margin-bottom:10px"
                title="自动验证默认关闭。每个验证器只执行判断认证状态所需的最小请求，不读取业务数据、不枚举资源。" />
      <el-table :data="verifiers" size="small">
        <el-table-column prop="id" label="ID" width="140" />
        <el-table-column prop="title" label="说明" min-width="220" />
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="适用类型" min-width="160"><template #default="{ row }">{{ row.supported_types.join(', ') }}</template></el-table-column>
        <el-table-column prop="endpoint" label="固定端点" min-width="200" />
      </el-table>
    </el-card>

    <el-row :gutter="14">
      <el-col :span="10">
        <el-card shadow="never" header="验证队列">
          <el-radio-group v-model="jobFilter" size="small" style="margin-bottom:8px" @change="loadJobs">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="queued">排队中</el-radio-button>
            <el-radio-button value="running">执行中</el-radio-button>
            <el-radio-button value="finished">已完成</el-radio-button>
          </el-radio-group>
          <el-table :data="jobs" size="small" max-height="420">
            <el-table-column prop="id" label="作业" width="60" />
            <el-table-column prop="preview" label="凭据" min-width="130" />
            <el-table-column prop="type" label="类型" width="130" />
            <el-table-column prop="verifier_id" label="验证器" width="110" />
            <el-table-column label="方式" width="70">
              <template #default="{ row }">{{ ({ single: '单条', batch: '批量', auto: '自动' } as any)[row.requested_by] }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">{{ STATUS_LABELS[row.status] || row.status }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!jobs.length" description="队列为空" :image-size="50" />
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card shadow="never" header="验证历史（追加式，不覆盖）">
          <el-table :data="history" size="small" max-height="470">
            <el-table-column prop="preview" label="凭据" min-width="130" />
            <el-table-column prop="type" label="类型" width="140" />
            <el-table-column label="结果" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="({ valid: 'success', invalid: 'danger' } as any)[row.status] || 'info'">
                  {{ STATUS_LABELS[row.status] || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="证据（不含响应体）" min-width="180">
              <template #default="{ row }">{{ JSON.stringify(row.evidence) }}</template>
            </el-table-column>
            <el-table-column label="耗时" width="80">
              <template #default="{ row }">{{ row.latency_ms ? row.latency_ms + 'ms' : '—' }}</template>
            </el-table-column>
            <el-table-column label="时间" width="165">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!history.length" description="暂无验证记录" :image-size="50" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import http, { fmtTime, STATUS_LABELS } from '../api'
import { onMounted, ref } from 'vue'

const verifiers = ref<any[]>([])
const jobs = ref<any[]>([])
const history = ref<any[]>([])
const jobFilter = ref('')

const loadJobs = async () => {
  jobs.value = (await http.get('/verification/jobs', { params: jobFilter.value ? { status: jobFilter.value } : {} })).data
  history.value = (await http.get('/verification/history')).data
}
onMounted(async () => {
  verifiers.value = (await http.get('/verification/verifiers')).data
  loadJobs()
  setInterval(loadJobs, 5000)
})
</script>
