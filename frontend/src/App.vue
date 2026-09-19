<template>
  <el-container style="height: 100vh">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <div class="brand-title">云凭据泄露检测</div>
        <div class="brand-sub">自动化检测与响应系统</div>
      </div>
      <el-menu :default-active="$route.path" router background-color="#1d2530" text-color="#c6cdd8"
               active-text-color="#409eff">
        <el-menu-item index="/"><el-icon><Odometer /></el-icon>总览</el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Monitor /></el-icon>监控任务</el-menu-item>
        <el-menu-item index="/findings"><el-icon><Key /></el-icon>发现列表</el-menu-item>
        <el-menu-item index="/verification"><el-icon><CircleCheck /></el-icon>验证中心</el-menu-item>
        <el-menu-item index="/channels"><el-icon><Grid /></el-icon>渠道与规则</el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon>设置</el-menu-item>
      </el-menu>
      <div class="footer-note">单机模式 · 默认不验证</div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ $route.meta.title }}</span>
        <span class="header-right">本地数据 · 界面默认脱敏</span>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { Odometer, Monitor, Key, CircleCheck, Grid, Setting } from '@element-plus/icons-vue'
</script>

<style>
body { margin: 0; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
.aside { background: #1d2530; color: #fff; }
.brand { padding: 18px 16px 12px; border-bottom: 1px solid #2c3644; }
.brand-title { font-size: 17px; font-weight: 700; color: #fff; }
.brand-sub { font-size: 12px; color: #8b95a5; margin-top: 4px; }
.footer-note { position: absolute; bottom: 14px; left: 16px; font-size: 12px; color: #66707f; }
.aside .el-menu { border-right: none; }
.header { background: #fff; border-bottom: 1px solid #e6e8eb; display: flex; align-items: center; justify-content: space-between; }
.page-title { font-size: 17px; font-weight: 600; }
.header-right { font-size: 12px; color: #98a1ad; }
.main { background: #f5f7fa; }
.card-row { margin-bottom: 14px; }
.stat-num { font-size: 26px; font-weight: 700; }
.stat-label { font-size: 13px; color: #7b8593; margin-top: 4px; }
</style>
