<template>
  <div>
    <el-tabs>
      <el-tab-pane label="渠道能力矩阵">
        <el-alert type="info" :closable="false" style="margin-bottom:10px"
                  title="状态口径：planned 规划支持 / implemented 代码已实现 / offline_tested 离线测试通过 / live_verified 真实接入验证通过" />
        <el-table :data="channels" size="small">
          <el-table-column prop="key" label="渠道标识" min-width="200" />
          <el-table-column prop="title" label="名称" min-width="140" />
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="({ offline_tested: 'success', implemented: 'primary', planned: 'info', live_verified: 'success', blocked: 'danger' } as any)[row.status]">
                {{ ({ blocked: 'blocked（外部受限）' } as any)[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="260">
            <template #default="{ row }">{{ JSON.stringify(row.meta) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="采集器">
        <el-table :data="collectors" size="small">
          <el-table-column prop="key" label="键" width="110" />
          <el-table-column prop="title" label="名称" min-width="160" />
          <el-table-column prop="category" label="渠道类别" width="130" />
          <el-table-column prop="platform" label="平台" width="110" />
          <el-table-column prop="version" label="版本" width="80" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="检测规则">
        <el-alert type="info" :closable="false" style="margin-bottom:10px"
                  title="禁用规则只影响后续扫描；规则测试使用内置正反样例，不会发起任何线上验证。" />
        <el-table :data="rules" size="small" max-height="560">
          <el-table-column prop="id" label="规则 ID" min-width="200" />
          <el-table-column prop="title" label="名称" min-width="180" />
          <el-table-column prop="type" label="凭据类型" min-width="180" />
          <el-table-column prop="vendor" label="厂商" width="110" />
          <el-table-column prop="version" label="版本" width="70" />
          <el-table-column prop="license" label="许可证" width="90" />
          <el-table-column prop="verifier_id" label="关联验证器" width="120" />
          <el-table-column label="启用" width="90">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="(v: any) => toggleRule(row, v)" />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import http from '../api'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const channels = ref<any[]>([])
const collectors = ref<any[]>([])
const verifiers = ref<any[]>([])
const rules = ref<any[]>([])

const load = async () => {
  const caps = (await http.get('/channels')).data
  channels.value = caps.capabilities
  collectors.value = caps.collectors
  verifiers.value = caps.verifiers
  rules.value = (await http.get('/rules')).data
}
onMounted(load)

const toggleRule = async (row: any, enabled: boolean) => {
  await http.patch(`/rules/${row.id}`, { enabled })
  row.enabled = enabled
  ElMessage.success(`${row.id} 已${enabled ? '启用' : '禁用'}`)
}
</script>
