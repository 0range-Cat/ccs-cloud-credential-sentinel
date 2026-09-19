<template>
  <div>
    <div class="card-row" style="display:flex;gap:10px">
      <el-button type="primary" @click="openCreate">新建来源</el-button>
      <el-button @click="uploadVisible = true">上传压缩包导入</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-card shadow="never" header="采集来源与任务">
      <el-table :data="sources" size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="collector_key" label="采集器" width="100" />
        <el-table-column label="模式" width="90">
          <template #default="{ row }">{{ row.task?.mode === 'manual' ? '手动' : '持续' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.task?.status)">{{ STATUS_LABELS[row.task?.status] || row.task?.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="间隔" width="80">
          <template #default="{ row }">{{ row.task?.interval_sec ? row.task.interval_sec + 's' : '—' }}</template>
        </el-table-column>
        <el-table-column label="上次运行" width="170">
          <template #default="{ row }">{{ fmtTime(row.task?.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="150">
          <template #default="{ row }"><span style="color:#f56c6c">{{ row.task?.last_error || '' }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="330">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="run(row)">立即运行</el-button>
            <el-button size="small" @click="action(row, 'pause')">暂停</el-button>
            <el-button size="small" @click="action(row, 'resume')">恢复</el-button>
            <el-button size="small" @click="action(row, 'cancel')">取消</el-button>
            <el-button size="small" @click="showRuns(row)">批次</el-button>
            <el-button size="small" type="danger" @click="del(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createVisible" title="新建采集来源" width="560">
      <el-form label-width="110px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如：我的GitHub演示仓库" /></el-form-item>
        <el-form-item label="采集器">
          <el-select v-model="form.collector_key" style="width:100%">
            <el-option label="GitHub 仓库扫描" value="github" />
            <el-option label="本地目录扫描" value="local_dir" />
          </el-select>
        </el-form-item>
        <template v-if="form.collector_key === 'github'">
          <el-form-item label="仓库"><el-input v-model="form.repo" placeholder="owner/repo 或完整 URL" /></el-form-item>
          <el-form-item label="分支"><el-input v-model="form.branch" placeholder="留空=默认分支" /></el-form-item>
          <el-alert type="info" :closable="false" title="Token 在【设置】页配置；未配置时匿名低频访问（60次/小时）" />
        </template>
        <template v-else>
          <el-form-item label="目录路径"><el-input v-model="form.path" placeholder="本机绝对路径" /></el-form-item>
        </template>
        <el-form-item label="模式">
          <el-radio-group v-model="form.mode">
            <el-radio value="manual">手动扫描</el-radio>
            <el-radio value="continuous">持续监控</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="间隔（秒）" v-if="form.mode === 'continuous'">
          <el-input-number v-model="form.interval_sec" :min="30" :step="30" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="上传压缩包导入（zip/tar）" width="480">
      <el-upload drag :http-request="doUpload" accept=".zip,.tar,.gz,.tgz" :show-file-list="false">
        <el-button type="primary">选择文件（≤200MB）</el-button>
      </el-upload>
    </el-dialog>

    <el-drawer v-model="runsVisible" :title="`批次记录（来源 #${runSource?.id}）`" size="55%">
      <el-table :data="runs" size="small">
        <el-table-column prop="id" label="批次" width="70" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">{{ STATUS_LABELS[row.status] || row.status }}</template>
        </el-table-column>
        <el-table-column label="开始" width="170"><template #default="{ row }">{{ fmtTime(row.started_at) }}</template></el-table-column>
        <el-table-column label="统计">
          <template #default="{ row }">
            <span style="font-family:monospace">{{ JSON.stringify(row.stats) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import http, { fmtTime, STATUS_LABELS } from '../api'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const sources = ref<any[]>([])
const createVisible = ref(false)
const uploadVisible = ref(false)
const runsVisible = ref(false)
const runs = ref<any[]>([])
const runSource = ref<any>(null)
const form = ref<any>({ name: '', collector_key: 'github', repo: '', branch: '', path: '', mode: 'manual', interval_sec: 300 })

const load = async () => { sources.value = (await http.get('/sources')).data }
onMounted(load)

const statusType = (s?: string) =>
  ({ running: 'primary', pending: 'info', done: 'success', completed: 'success', failed: 'danger', paused: 'warning', cancelled: 'info' } as any)[s || ''] || 'info'

const openCreate = () => { form.value = { name: '', collector_key: 'github', repo: '', branch: '', path: '', mode: 'manual', interval_sec: 300 }; createVisible.value = true }

const create = async () => {
  const f = form.value
  const config: any = f.collector_key === 'github' ? { repo: f.repo } : { path: f.path }
  if (f.collector_key === 'github' && f.branch) config.branch = f.branch
  await http.post('/sources', { name: f.name || '未命名', collector_key: f.collector_key, config, mode: f.mode, interval_sec: f.interval_sec })
  createVisible.value = false
  ElMessage.success('已创建')
  load()
}

const run = async (row: any) => {
  try {
    await http.post(`/sources/${row.id}/run`)
    ElMessage.success('已执行完成')
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '执行失败') }
  load()
}

const action = async (row: any, act: string) => {
  await http.post(`/tasks/${row.task.id}/${act}`)
  load()
}

const del = async (row: any) => {
  await ElMessageBox.confirm('删除来源会同时删除其任务与批次记录，确认？', '删除', { type: 'warning' })
  await http.delete(`/sources/${row.id}`)
  load()
}

const showRuns = async (row: any) => {
  runSource.value = row
  runs.value = (await http.get(`/tasks/${row.task.id}/runs`)).data
  runsVisible.value = true
}

const doUpload = async (opt: any) => {
  const fd = new FormData()
  fd.append('upload', opt.file)
  await http.post('/import/archive', fd)
  ElMessage.success('已上传并完成扫描')
  uploadVisible.value = false
  load()
}
</script>
