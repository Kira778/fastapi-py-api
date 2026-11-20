# FastAPI Task API

一个用于配套 FastAPI 四篇实战系列的异步任务管理服务。它包含 PostgreSQL、JWT 鉴权、Redis 任务详情缓存，以及 Celery 导出任务。

## 快速开始

```powershell
Copy-Item .env.example .env
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

## 测试

```powershell
uv run pytest
```

## 使用 Docker Compose

`.env` 中的数据库与 Redis 主机名应保持为 `postgres` 和 `redis`。

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose 会启动 API、PostgreSQL、Redis 和 Celery worker。API 启动时自动执行迁移。

## 接口摘要

- `POST /api/v1/auth/register` 注册用户
- `POST /api/v1/auth/login` 获取 Bearer JWT
- `GET /api/v1/auth/me` 查看当前用户
- `/api/v1/tasks` 提供任务 CRUD、分页与状态筛选
- `POST /api/v1/exports/tasks` 提交 CSV 导出
- `GET /api/v1/exports/tasks/{task_id}` 查询导出状态和结果

Redis 仅缓存任务详情五分钟。修改和删除任务会删除对应用户的缓存键。导出结果适合教学与小数据量场景，大文件应写入对象存储并返回下载链接。
