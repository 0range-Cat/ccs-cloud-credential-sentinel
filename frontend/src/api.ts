import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

export function fmtTime(iso?: string | null): string {
  if (!iso) return '未知'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '未知'
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}

export function fmtSeconds(s?: number | null): string {
  if (s === null || s === undefined) return '—'
  if (s < 60) return `${s.toFixed(0)} 秒`
  if (s < 3600) return `${(s / 60).toFixed(1)} 分钟`
  return `${(s / 3600).toFixed(1)} 小时`
}

export const STATUS_LABELS: Record<string, string> = {
  pending: '待处理', confirmed: '已确认', false_positive: '误报', ignored: '已忽略',
  not_requested: '未验证', queued: '排队中', running: '执行中', valid: '有效',
  invalid: '无效', inconclusive: '无法判断', missing_context: '缺少配对信息',
  unsupported: '不支持验证', rate_limited: '受限流', network_error: '网络错误',
  error: '验证异常', completed: '已完成', failed: '失败', cancelled: '已取消',
  interrupted: '被中断', paused: '已暂停', done: '已完成',
}

export default http
