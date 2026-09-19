<template>
  <el-row :gutter="14">
    <el-col :span="12">
      <el-card shadow="never" header="平台采集账号" class="card-row">
        <el-form label-width="140px">
          <el-form-item label="GitHub Token">
            <el-input v-model="form['platform.github.token']" type="password" show-password
                      placeholder="只读 PAT；加密存储，留空表示清除" />
            <div class="tip">用于采集与连接测试；与扫描发现的凭据分开管理。</div>
          </el-form-item>
          <el-form-item label="Gitee Token">
            <el-input v-model="form['platform.gitee.token']" type="password" show-password
                      placeholder="阶段2 启用；加密存储" disabled />
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" header="网络与并发" class="card-row">
        <el-form label-width="140px">
          <el-form-item label="代理地址"><el-input v-model="form['network.proxy']" placeholder="http://127.0.0.1:7890，留空直连" /></el-form-item>
          <el-form-item label="请求超时（秒）"><el-input-number v-model="form['network.timeout_seconds']" :min="5" :max="120" /></el-form-item>
          <el-form-item label="单主机速率（次/秒）"><el-input-number v-model="form['network.rate_per_host_per_sec']" :min="0.2" :max="20" :step="0.5" /></el-form-item>
          <el-form-item label="工作器数量"><el-input-number v-model="workers" :min="1" :max="16" disabled />
            <div class="tip">通过环境变量 CCS_WORKERS 配置（需重启）。</div>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" header="扫描预算默认值" class="card-row">
        <el-form label-width="140px">
          <el-form-item label="单次最大内容数"><el-input-number v-model="form['scan.max_items']" :min="10" :step="100" /></el-form-item>
          <el-form-item label="单次最大字节"><el-input-number v-model="form['scan.max_bytes']" :min="1048576" :step="10485760" /></el-form-item>
          <el-form-item label="单次最长时间（秒）"><el-input-number v-model="form['scan.max_seconds']" :min="60" :step="300" /></el-form-item>
          <el-form-item label="单文件上限（字节）"><el-input-number v-model="form['scan.max_file_bytes']" :min="10240" :step="102400" /></el-form-item>
        </el-form>
      </el-card>
    </el-col>

    <el-col :span="12">
      <el-card shadow="never" header="验证策略" class="card-row">
        <el-alert type="warning" :closable="false" style="margin-bottom:10px"
                  title="默认关闭自动验证。开启后仅对有最小验证器的类型按策略执行，且绝不读取业务数据或枚举资源。" />
        <el-form label-width="180px">
          <el-form-item label="自动验证">
            <el-switch v-model="form['verification.auto_enabled']" />
          </el-form-item>
          <el-form-item label="验证并发"><el-input-number v-model="form['verification.concurrency']" :min="1" :max="16" /></el-form-item>
          <el-form-item label="每分钟最多验证"><el-input-number v-model="form['verification.max_per_minute']" :min="1" :max="120" /></el-form-item>
          <el-form-item label="重新验证间隔（天）"><el-input-number v-model="form['verification.reverify_days']" :min="1" :max="365" /></el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" header="脱敏与导出" class="card-row">
        <el-form label-width="180px">
          <el-form-item label="界面默认脱敏"><el-switch v-model="form['masking.enabled']" /></el-form-item>
          <el-form-item label="导出默认脱敏"><el-switch v-model="form['export.default_masked']" /></el-form-item>
          <el-form-item label="界面时区"><el-input v-model="form['display.timezone']" placeholder="Asia/Shanghai" /></el-form-item>
          <el-form-item label="缓存保留（天）"><el-input-number v-model="form['retention.cache_days']" :min="1" :max="365" /></el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" header="采集连接测试" class="card-row">
        <el-alert type="info" :closable="false" style="margin-bottom:8px"
                  title="连接测试只使用上面配置的采集账号，绝不使用扫描发现的凭据。" />
        <el-form inline>
          <el-form-item>
            <el-select v-model="testTarget" style="width:160px">
              <el-option label="GitHub" value="github" />
              <el-option label="本地目录" value="local_dir" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-input v-model="testConfig" :placeholder="testTarget === 'github' ? 'owner/repo' : '目录路径'" style="width:260px" />
          </el-form-item>
          <el-form-item><el-button type="primary" @click="test">测试</el-button></el-form-item>
        </el-form>
        <el-alert v-if="testResult" :title="testResult" :type="testOk ? 'success' : 'error'" :closable="false" />
      </el-card>

      <el-button type="primary" size="large" style="margin-top:10px" :loading="saving" @click="save">保存全部设置</el-button>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import http from '../api'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const settings = ref<any>({})
const form = ref<any>({})
const workers = ref(2)
const saving = ref(false)
const testTarget = ref('local_dir')
const testConfig = ref('')
const testResult = ref('')
const testOk = ref(false)

onMounted(async () => {
  settings.value = (await http.get('/settings')).data
  const f: any = {}
  for (const [k, v] of Object.entries<any>(settings.value)) f[k] = v.value ?? ''
  form.value = f
})

const save = async () => {
  saving.value = true
  try {
    await http.put('/settings', { values: form.value })
    ElMessage.success('已保存（敏感项已加密存储）')
  } finally { saving.value = false }
}

const test = async () => {
  const resp = await http.post('/settings/test-connection', {
    target: testTarget.value,
    config: testTarget.value === 'github' ? { repo: testConfig.value } : { path: testConfig.value },
  })
  testOk.value = resp.data.ok
  testResult.value = resp.data.message
}
</script>

<style scoped>
.tip { font-size: 12px; color: #98a1ad; line-height: 1.4; }
</style>
