# Atlas 路演优先版需求与接口文档

版本：v0.1  
目标读者：产品、Web、macOS、后端、路演演示人员  
当前正式 API：`/api/v1`  
当前影子环境：`/shadow/api/v1`（Caddy 会移除 `/shadow` 前缀）

## 1. 目标与范围

本阶段的第一目标不是承载大规模生产流量，而是在路演现场稳定展示一条“真实数据、跨页面联动、权限可信”的共创闭环：

1. 新用户完成注册、验证和登录。
2. 用户创建或加入一个企划，并在星图中看到真实企划。
3. 企主发布互动任务，成员接取并投稿。
4. 投稿涉及他人角色时进入共同确认。
5. 企主审核通过后，同步更新 Wiki、Canvas、贡献记录和通知。
6. 用户能在企划首页和个人视角看到该企划内的贡献结果。

不进入路演 P0：私信、实时多人编辑、CRDT、链上认证、手机号登录、复杂搜索推荐、完整通用 AI Agent、生产级风控和大规模运维。

## 2. 优先级与实施顺序

| 阶段 | 目标 | 功能 |
|---|---|---|
| P0-A | 可进入、可看到真实数据 | 注册登录、用户资料、企划星图、空态/错误态 |
| P0-B | 可完成核心共创闭环 | 成员权限、任务状态机、投稿、共同确认、审核 |
| P0-C | 可体现 Atlas 差异 | Wiki/Canvas 同源、通知、企划内贡献榜 |
| P0-D | 增强路演表现 | 资产手动上传、受控 Canvas AI 指令 |
| P1 | 内测可用 | 邮件送达、GitHub OAuth、资产版本、Wiki 差异/恢复、任务截止处理 |
| P2 | 生产完善 | 限流、反滥用、内容安全、可观测性、COS 清理补偿、完整灾备 |

推荐开发顺序：`身份 → 用户资料/星图 → 成员权限 → 任务 → 投稿/确认/审核 → Wiki/Canvas → 通知 → 贡献 → 资产 → AI`。

## 3. 通用接口约定

- JSON 字段：服务端请求使用 `snake_case`，响应对前端保持稳定的 `camelCase`。
- 认证：短期 Bearer Access Token；Refresh Token 仅存于 HttpOnly Cookie。
- 所有请求携带或返回 `x-request-id`，错误响应包含 `requestID`。
- 更新型资源携带 `expected_revision`；版本冲突返回 HTTP `409 REVISION_CONFLICT`。
- 列表统一返回 `{ items, nextCursor }`，路演阶段允许首屏固定 `limit=30`。
- 错误统一为：

```json
{
  "error": { "code": "STABLE_CODE", "message": "用户可读说明", "details": {} },
  "requestID": "uuid"
}
```

前端必须分别呈现加载态、空态、权限态、冲突态和服务错误，不得回退到样例数据。

## 4. 用户注册、登录与资料

### 4.1 路演 P0

- 邮箱注册：用户名、显示名、邮箱、密码。
- 邮箱验证：开发/路演环境可由管理员生成验证链接；公开上线必须真实发信。
- 用户名或邮箱登录。
- Access Token 失效时自动刷新一次；刷新失败返回登录页。
- 登出撤销刷新会话。
- 资料页展示：显示名、用户名、头像、简介、标签、参与/管理的企划。
- 编辑：显示名、简介、头像、横幅、标签。

### 4.2 接口

已有：

- `POST /auth/register`
- `POST /auth/verify-email`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `POST /auth/change-password`
- `GET /auth/me`
- `GET /auth/github/start`

需补：

- `GET /users/me/profile`
- `PATCH /users/me/profile`
- `GET /users/{user_id}/profile`
- `GET /users/me/worlds?role=managed|joined`

资料响应建议：

```json
{
  "id": "uuid",
  "username": "cen",
  "displayName": "岑",
  "avatarUrl": null,
  "bannerUrl": null,
  "bio": "...",
  "tags": ["世界观", "写作"],
  "revision": 3
}
```

### 4.3 验收

- 未验证邮箱不可密码登录，并给出明确提示。
- 刷新页面可通过 Refresh Cookie 恢复登录。
- 用户 A 不可修改用户 B 的资料。
- 资料为空时展示真实空态，不显示“岑”等硬编码身份。

## 5. 企划星图与企划数据

### 5.1 P0 展示规则

- “我的世界”显示本人拥有或加入的企划。
- “发现/星图”仅显示 `visibility=public` 且非草稿的企划。
- 卡片字段：名称、标语、封面、状态、进度、成员数、当前用户角色。
- 路演可以预置一份明确标记的演示种子数据，但不得混入用户私有列表，也不得在前端硬编码。

已有接口：

- `GET /worlds`
- `POST /worlds`
- `GET /worlds/{world_id}`
- `PATCH /worlds/{world_id}`

需补：

- `GET /worlds/discover?cursor=&limit=`
- `GET /worlds/{world_id}/summary`：成员数、任务数、对象数、贡献者摘要。

`GET /worlds` 应增加明确过滤参数：`scope=mine|discover`，避免客户端自行混合公开与成员企划。

### 5.2 验收

- 私密企划不会出现在非成员星图。
- 已归档企划只读。
- Web 与 macOS 使用同一企划 ID、revision 和封面地址。

## 6. 成员类型、权限分配与管理

角色定义：

| 能力 | 企主 owner | 管理成员 manager | 参企者 participant | 观察者 observer | 游客 |
|---|---:|---:|---:|---:|---:|
| 查看公开内容 | ✓ | ✓ | ✓ | ✓ | 仅公开 |
| 编辑 Canvas/Wiki | ✓ | ✓ | ✓ | — | — |
| 发布/管理任务 | ✓ | ✓ | — | — | — |
| 接取任务/投稿 | ✓ | ✓ | ✓ | — | — |
| 审核投稿 | ✓ | 可配置，P0 默认 ✓ | — | — | — |
| 管理成员 | ✓ | 除企主外 | — | — | — |
| 转移所有权/归档 | ✓ | — | — | — | — |

已有接口覆盖成员列表、邀请、加入申请、角色调整、移除和所有权转移。需增加：

- `GET /worlds/{world_id}/permissions/me`，返回前端可直接使用的能力集合。
- 审核操作必须在服务端再次校验，不信任前端隐藏按钮。
- 最后一个企主不可退出；转移所有权必须原企主本人确认。

## 7. 用户间共同确认

共同确认不是私信，是投稿审核前的业务关卡。

触发条件：投稿的 `affected_object_ids` 中包含互动策略为 `review` 且属于其他用户的角色。服务端为每个相关角色生成一条 `SubmissionConfirmation`。

状态：`pending → accepted | declined`。

- 全部 accepted：投稿进入 `owner_review`。
- 任一 declined：投稿进入 `confirmation_rejected`，作者可修改后重新提交。
- `forbidden` 角色不可被加入投稿，创建时直接拒绝。
- 同一用户拥有多个涉及角色时可以一次确认，底层仍保留逐角色记录。

已有接口：

- `GET /interaction-confirmations`
- `PATCH /interaction-confirmations/{submission_id}/{character_profile_id}`

需补：

- `POST /worlds/{world_id}/submissions/{submission_id}/resubmit`
- 确认列表响应补充投稿标题、企划名称、角色名称、作者摘要和跳转目标。

## 8. Wiki 与 Canvas 同源优化

`world_objects` 是唯一正式内容源；Canvas 是对象与关系的空间投影，Wiki 是对象的结构化编辑视图。两端不能拥有独立业务真相。

P0 数据模型：

- `WorldObject`：`id, world_id, kind, title, payload, revision, updated_by`。
- `WikiRevision`：不可变历史，保存作者、标题、payload 和 revision。
- `CanvasDocument`：对象布局、关系和视觉属性；保存时同步对象核心字段。
- JSON 必须携带 `schemaVersion`。

已有接口覆盖对象列表、对象保存、版本列表、Canvas 获取/保存。P0 需补：

- `GET /worlds/{world_id}/objects/{object_id}`。
- 对象详情按 `kind` 校验结构化属性。
- Wiki 保存返回最新对象 revision 与 Canvas revision。
- 前端 409 时展示“刷新最新版本/保留当前草稿”，禁止静默覆盖。

P1 增加版本差异与恢复：

- `GET .../revisions/{revision}`
- `GET .../diff?from=&to=`
- `POST .../revisions/{revision}/restore`

## 9. 通知（站内信）

只做系统通知、业务通知和待确认事项，不做用户私信。

通知类型至少包括：邀请、加入申请、角色变更、任务状态、投稿状态、共同确认、审核结果、Wiki 更新。字段包括 `type, title, summary, worldID, actionType, actionTarget, dedupeKey, readAt, archivedAt`。

已有接口：分页列表、单条已读、全部已读、归档。需优化：

- `unreadCount` 必须由服务端返回。
- 相同业务事件使用 `dedupeKey` 去重。
- `actionTarget` 使用结构化路由，如 `{ worldID, screen, resourceID }`。
- 待确认与普通通知在 UI 分组，但仍使用同一通知基础设施。
- 前端不得显示写死的收件箱内容。

P0 验收：审核/确认动作完成后，相关用户刷新通知列表即可看到唯一通知；点击能进入正确企划和对象。

## 10. 互动任务状态机

任务状态：

```text
draft → open → active → settling → completed
             ↘ cancelled
```

- `draft`：仅企主/管理员可见和编辑。
- `open`：可接取；达到 capacity 后自动变为 active。
- `active`：已接取成员可投稿，也可在未投稿前放弃。
- `settling`：停止新接取，等待已有投稿审核。
- `completed`：所有有效工作已结算，只读。
- `cancelled`：只读，并通知已接取成员。

成员任务状态：`joined → submitted → revision_requested → resubmitted → accepted | withdrawn`。

已有接口：任务创建/更新、接取、放弃、列表。需补：

- 列表返回 `joinedByMe, participantCount, myAssignmentStatus`。
- 放弃仅允许尚无待审投稿的成员；有投稿时先撤回。
- `POST /worlds/{world_id}/tasks/{task_id}/complete` 使用明确命令接口，避免客户端任意写状态。
- 状态迁移集中在领域服务中，不允许路由层直接赋值。

## 11. 投稿与审核

投稿状态建议统一为：

```text
draft → awaiting_confirmation → owner_review → accepted
                      ↘ confirmation_rejected
owner_review → revision_requested → owner_review
             ↘ rejected
任意待审状态 → withdrawn
```

P0 投稿字段：任务、标题、正文、目标 Wiki 对象、变更类型、涉及对象、附件、revision、作者。

审核通过必须在一个数据库事务中完成：

1. 锁定投稿并校验状态/revision。
2. 创建或更新 `world_objects`。
3. 写入 WikiRevision。
4. 更新 CanvasDocument revision。
5. 写入 ContributionEvent。
6. 创建通知与审计事件。

已有接口覆盖创建、修改、撤回、审核。需补重新提交接口，并将审核评分参数从页面隐式默认值改为清晰表单或后端规则。

验收：重复点击审核不会生成重复贡献；共同确认未完成时服务端拒绝企主审核；拒绝和退修必须保存原因。

## 12. 企划内贡献系统

贡献必须以 `world_id` 隔离，不提供跨企划可直接比较的总分。事件来源为审核通过、Wiki 有效修改、任务完成及后续认可的论坛互动。

事件建议字段：`worldID, userID, sourceType, sourceID, module, scale, completion, specialty, bonus, occurredAt`。同一来源使用唯一约束防止重复计分。

计分展示：

```text
score = scale + completion + specialty + bonus
```

P0 接口：

- 已有 `GET /worlds/{world_id}/contributions`。
- 需补 `GET /worlds/{world_id}/contributors?limit=12`。
- 需补 `GET /worlds/{world_id}/contributions/me`。

企划首页头像排序：贡献分降序；同分按最近贡献时间降序；再按用户 ID 稳定排序。企主不应因身份固定置顶，可单独显示 owner 标识。返回 `rank, user, score, moduleScores, lastContributedAt`。

权限：成员可看本企划排行榜和自己的明细；企主/管理员可看全部事件；游客仅在企划配置公开贡献时查看汇总。

## 13. 用户手动上传资产

P0 流程：选择文件 → 客户端校验 → 请求签名 → 直传 COS → 通知服务端完成 → 资产库出现条目。

已有接口：

- `POST /worlds/{world_id}/uploads/sign`
- `POST /worlds/{world_id}/assets`
- `GET /worlds/{world_id}/assets`
- `POST /worlds/{world_id}/assets/{asset_id}/versions`
- `POST /worlds/{world_id}/assets/{asset_id}/references`
- `DELETE /worlds/{world_id}/assets/{asset_id}`

P0 前端要求：上传进度、失败重试、类型/大小提示、取消、真实空态。支持图片、PDF、文本和常见音视频；限制以服务端签名接口为准。资产必须记录上传者、企划、版本、类型、大小、checksum 和引用对象。

路演环境若 COS 尚未配置，可提供明确的“资产服务未配置”状态，不允许伪造上传成功。

## 14. Canvas AI API

路演 P0 不追求通用 Agent，采用受控指令保证稳定：

- 根据一句描述生成若干草稿对象。
- 为选中对象补充简介或结构化字段。
- 建议对象关系，但由用户确认后写入。
- AI 永远只返回 proposal，不直接修改正式数据。

建议接口：`POST /worlds/{world_id}/ai/canvas/proposals`。

请求：

```json
{
  "instruction": "补充港口城市与灯塔的关系",
  "selectedObjectIDs": ["city-1", "lighthouse-1"],
  "canvasRevision": 7,
  "schemaVersion": 1
}
```

响应包含 `proposalID, operations[], explanation, basedOnRevision`。操作限定为 `createObject, updateObject, createRelation`。用户点击采纳时调用普通 Canvas 保存接口并携带 revision；若期间内容已更新则返回 409。

需补：请求超时、供应商错误映射、调用限额、审计、敏感配置隔离。旧 NestJS DeepSeek 接口在 Python 版本完成前不得作为新的独立写入源。

## 15. 路演演示数据与流程

准备三个账号：企主、角色拥有者、投稿成员；一个公开企划；两个角色；一个开放任务。演示数据必须由后端 seed 命令建立，并标记 `demo=true`，可重复清理和重建。

推荐 5 分钟演示：

1. 成员登录，在星图打开企划并接取任务。
2. 投稿涉及另一用户角色的内容。
3. 切换角色拥有者完成共同确认，通知即时更新。
4. 切换企主审核通过。
5. 展示 Wiki 与 Canvas 同步、贡献头像排序和个人贡献明细。
6. 可选展示手动上传资产或 AI proposal。

路演必须准备：稳定演示账号、数据库快照、一键 seed、一键恢复、录屏兜底；现场不依赖 GitHub OAuth、真实邮件或不可控的开放式 AI 输出。

## 16. 团队拆分建议

- 后端 A：用户资料、星图查询、权限能力接口。
- 后端 B：任务/投稿/确认/审核状态机与事务。
- Web：登录恢复、真实空态、主闭环页面和 API DTO 适配。
- macOS：共享 API Client、Keychain、同一 DTO/schemaVersion。
- 联调负责人：契约用例、演示 seed、路演脚本和回归清单。

每个接口合并前必须包含：权限测试、跨企划隔离测试、正常/空/冲突/越权响应，以及至少一个 Web 或 macOS 消费方的契约验证。

## 17. P0 完成定义

- 前端关键页面不读取 `samples/mock/sessionStorage` 作为权威业务数据。
- 三账号可完整走通任务、投稿、共同确认、审核、Wiki/Canvas、通知和贡献闭环。
- 所有写操作执行服务端对象级权限和企划隔离。
- 刷新页面后数据不丢失；双端读取同一结果。
- 演示 seed 可重复执行，健康检查和恢复脚本可在路演前完成。
- 影子环境回归通过后才讨论替换当前 NestJS `/api/*` 正式流量。
