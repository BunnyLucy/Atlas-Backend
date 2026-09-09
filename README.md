# Atlas Backend

Atlas Web 与 macOS 共用的 Python API。该仓库正在与旧 NestJS 后端并行建设，正式流量在契约测试和回滚演练完成前不会切换。

## 技术栈

- Python 3.13、FastAPI、Pydantic v2
- SQLAlchemy 2 Async、asyncpg、PostgreSQL、Alembic
- pytest、HTTPX、Testcontainers

## 本地运行

```bash
cp .env.example .env
docker compose up --build
```

API：`http://127.0.0.1:8790`；文档：`http://127.0.0.1:8790/docs`。

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest
```

管理员通过显式环境变量初始化，不在代码或数据库迁移中保存默认密码：

```bash
ATLAS_BOOTSTRAP_ADMIN_USERNAME=... \
ATLAS_BOOTSTRAP_ADMIN_EMAIL=... \
ATLAS_BOOTSTRAP_ADMIN_PASSWORD=... \
python scripts/bootstrap_admin.py
```

仅迁移本地旧开发账号时，可以临时设置 `ATLAS_BOOTSTRAP_ALLOW_LEGACY_PASSWORD=true`；生产环境不得启用。

## 当前边界

- 正式 API 使用 `/api/v1`；旧 Web 的 `/api/*` 兼容路由将在对应领域迁移时加入。
- Canvas 与 Wiki 共享世界对象，并使用 revision 乐观锁；冲突返回 HTTP 409。
- 产品不提供用户私信，只提供业务通知与待确认事项。
- Redis、多人实时协作、链上认证和完整 AI Agent 不属于首发范围。

## 腾讯云影子环境

`deploy/compose.shadow.yaml` 使用独立数据库卷运行 API 与 outbox worker，并仅通过 `atlas_default` 网络与现有 Caddy 连接。服务器准备好 `shared/.env.production` 后执行：

```bash
sudo ./scripts/deploy-shadow.sh
```

该脚本不会切换现有 `/api/*` 正式流量。Caddy 将 `/shadow/*` 去除前缀后转发到
`atlas-python-api-1:8790`，因此影子健康检查为 `/shadow/health`，正式健康检查仍为 `/health`。
