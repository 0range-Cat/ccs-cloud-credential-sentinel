# syntax=docker/dockerfile:1
# 云上凭据泄露自动化检测与响应系统 —— 多阶段构建
# 阶段1：构建前端；阶段2：Python 运行时托管 API + 静态界面
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    CCS_DATA_DIR=/app/data \
    CCS_STATIC_DIR=/app/static
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY backend/alembic.ini backend/alembic ./
COPY --from=ui /ui/dist ./static
VOLUME /app/data
EXPOSE 8000
# 应用启动时自动执行 Alembic 迁移并同步规则/能力清单
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
