<template>
  <div>
    <div class="card-row" style="display:flex;gap:10px">
      <el-button type="primary" @click="openCreate">新建来源</el-button>
      <el-button type="success" @click="seedVisible = true">种子发现</el-button>
      <el-button @click="uploadVisible = true">上传压缩包导入</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-card shadow="never" header="采集来源与任务">
      <el-table :data="sources" size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="collector_key" label="采集器" width="110" />
        <el-table-column label="模式" width="80">
          <template #default="{ row }">{{ row.task?.mode === 'manual' ? '手动' : '持续' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.task?.status)">{{ STATUS_LABELS[row.task?.status] || row.task?.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上次运行" width="165">
          <template #default="{ row }">{{ fmtTime(row.task?.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="140">
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

    <el-dialog v-model="createVisible" title="新建采集来源" width="580">
      <el-form label-width="110px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如：我的GitHub演示仓库" /></el-form-item>
        <el-form-item label="采集器">
          <el-select v-model="form.collector_key" style="width:100%">
            <el-option label="GitHub 仓库扫描" value="github" />
            <el-option label="Gitee 仓库扫描" value="gitee" />
            <el-option label="MediaWiki 站点监控" value="mediawiki" />
            <el-option label="通用 RSS/URL/Sitemap" value="generic_web" />
            <el-option label="Stack Overflow 关键词" value="stackoverflow" />
            <el-option label="本地目录扫描" value="local_dir" />
          </el-select>
        </el-form-item>
        <template v-if="form.collector_key === 'github'">
          <el-form-item label="仓库"><el-input v-model="form.repo" placeholder="owner/repo 或完整 URL" /></el-form-item>
          <el-form-item label="分支"><el-input v-model="form.branch" placeholder="留空=默认分支" /></el-form-item>
          <el-form-item label="扫描提交历史">
            <el-switch v-model="form.fetch_history" />
            <span class="tip" style="margin-left:8px">新提交优先，游标增量；耗时较长</span>
          </el-form-item>
          <el-alert type="info" :closable="false" title="Token 在【设置】页配置；未配置时匿名低频访问（60次/小时）" />
        </template>
        <template v-else-if="form.collector_key === 'gitee'">
          <el-form-item label="仓库"><el-input v-model="form.repo" placeholder="owner/repo 或完整 URL" /></el-form-item>
          <el-form-item label="分支"><el-input v-model="form.branch" placeholder="留空=默认分支" /></el-form-item>
        </template>
        <template v-else-if="form.collector_key === 'mediawiki'">
          <el-form-item label="API 地址"><el-input v-model="form.api_url" placeholder="https://站点/w/api.php" /></el-form-item>
          <el-form-item label="命名空间"><el-input v-model="form.namespaces" placeholder="0=正文页面，多个用 | 分隔" /></el-form-item>
        </template>
        <template v-else-if="form.collector_key === 'generic_web'">
          <el-form-item label="采集类型">
            <el-radio-group v-model="form.web_kind">
              <el-radio value="rss">RSS/Atom</el-radio>
              <el-radio value="sitemap">Sitemap</el-radio>
              <el-radio value="url">单页 URL</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="地址">
            <el-input v-model="form.web_url" placeholder="订阅源/站点地图/页面完整地址" />
          </el-form-item>
        </template>
        <template v-else-if="form.collector_key === 'stackoverflow'">
          <el-form-item label="关键词"><el-input v-model="form.q" placeholder="如泄露凭据相关的检索词" /></el-form-item>
          <el-form-item label="标签（可选）"><el-input v-model="form.tagged" placeholder="如 security;api" /></el-form-item>
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

    <el-dialog v-model="seedVisible" title="种子发现（一次生成多渠道任务）" width="640">
      <el-form label-width="130px" label-position="top">
        <el-form-item label="GitHub 仓库（每行一个 owner/repo）">
          <el-input v-model="seedForm.github_repos" type="textarea" :rows="2" placeholder="octocat/Hello-World" />
        </el-form-item>
        <el-form-item label="Gitee 仓库（每行一个）">
          <el-input v-model="seedForm.gitee_repos" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="MediaWiki API 地址（每行一个）">
          <el-input v-model="seedForm.wiki_api_urls" type="textarea" :rows="2" placeholder="https://zh.wikipedia.org/w/api.php" />
        </el-form-item>
        <el-form-item label="RSS/Atom 订阅源（每行一个）">
          <el-input v-model="seedForm.feeds" type="textarea" :rows="2" placeholder="https://feed.cnblogs.com/blog/sitehome/rss" />
        </el-form-item>
        <el-form-item label="Sitemap（每行一个）">
          <el-input v-model="seedForm.sitemaps" type="textarea" :rows="1" />
        </el-form-item>
        <el-form-item label="Stack Overflow 关键词（每行一个）">
          <el-input v-model="seedForm.stackoverflow_keywords" type="textarea" :rows="1" />
        </el-form-item>
        <el-form-item>
          <el-radio-group v-model="seedForm.mode">
            <el-radio value="manual">手动</el-radio>
            <el-radio value="continuous">持续监控</el-radio>
          </el-radio-group>
          <el-input-number v-model="seedForm.interval_sec" :min="30" :step="30" style="margin-left:12px" />
          <span class="tip" style="margin-left:8px">秒</span>
        </el-form-item>
        <el-alert type="info" :closable="false"
                  title="纯关键词只生成 Stack Overflow 监控；GitHub/Gitee 代码搜索需认证且结果有上限，不做无认证批量搜索。" />
      </el-form>
      <template #footer>
        <el-button @click="seedVisible = false">取消</el-button>
        <el-button type="primary" @click="createSeed">生成任务</el-button>
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
const seedVisible = ref(false)
const uploadVisible = ref(false)
const runsVisible = ref(false)
const runs = ref<any[]>([])
const runSource = ref<any>(null)
const blankForm = () => ({ name: '', collector_key: 'github', repo: '', branch: '', path: '',
  api_url: '', namespaces: '', web_kind: 'rss', web_url: '', q: '', tagged: '',
  fetch_history: false, mode: 'manual', interval_sec: 300 })
const form = ref<any>(blankForm())
const seedForm = ref<any>({ github_repos: '', gitee_repos: '', wiki_api_urls: '', feeds: '',
  sitemaps: '', urls: '', stackoverflow_keywords: '', mode: 'manual', interval_sec: 300 })

const load = async () => { sources.value = (await http.get('/sources')).data }
onMounted(load)

const statusType = (s?: string) =>
  ({ running: 'primary', pending: 'info', done: 'success', completed: 'success', failed: 'danger', paused: 'warning', cancelled: 'info' } as any)[s || ''] || 'info'

const openCreate = () => { form.value = blankForm(); createVisible.value = true }

const buildConfig = (f: any) => {
  if (f.collector_key === 'github') {
    const c: any = { repo: f.repo }
    if (f.branch) c.branch = f.branch
    if (f.fetch_history) { c.fetch_history = true; c.history_max_commits = 20 }
    return c
  }
  if (f.collector_key === 'gitee') {
    const c: any = { repo: f.repo }
    if (f.branch) c.branch = f.branch
    return c
  }
  if (f.collector_key === 'mediawiki') {
    const c: any = { api_url: f.api_url }
    if (f.namespaces) c.namespaces = f.namespaces
    return c
  }
  if (f.collector_key === 'generic_web') {
    return f.web_kind === 'rss' ? { feed_url: f.web_url }
      : f.web_kind === 'sitemap' ? { sitemap_url: f.web_url }
      : { url: f.web_url }
  }
  if (f.collector_key === 'stackoverflow') {
    const c: any = { q: f.q }
    if (f.tagged) c.tagged = f.tagged
    return c
  }
  return { path: f.path }
}

const create = async () => {
  const f = form.value
  await http.post('/sources', { name: f.name || '未命名', collector_key: f.collector_key,
    config: buildConfig(f), mode: f.mode, interval_sec: f.interval_sec })
  createVisible.value = false
  ElMessage.success('已创建')
  load()
}

const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean)

const createSeed = async () => {
  const s = seedForm.value
  const body = {
    github_repos: lines(s.github_repos), gitee_repos: lines(s.gitee_repos),
    wiki_api_urls: lines(s.wiki_api_urls), feeds: lines(s.feeds),
    sitemaps: lines(s.sitemaps), urls: lines(s.urls),
    stackoverflow_keywords: lines(s.stackoverflow_keywords),
    mode: s.mode, interval_sec: s.interval_sec,
  }
  if (!body.github_repos.length && !body.gitee_repos.length && !body.wiki_api_urls.length &&
      !body.feeds.length && !body.sitemaps.length && !body.urls.length && !body.stackoverflow_keywords.length) {
    ElMessage.warning('请至少填写一个目标')
    return
  }
  const resp = await http.post('/discover/seed', body)
  ElMessage.success(`已生成 ${resp.data.count} 个来源任务`)
  seedVisible.value = false
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

<style scoped>
.tip { font-size: 12px; color: #98a1ad; }
</style>
