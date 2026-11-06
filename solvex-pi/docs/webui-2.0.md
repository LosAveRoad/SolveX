# WebUI 2.0 使用说明

启动：

```bash
npx tsx apps/cli/src/index.ts serve --port 8000
# 凭据在「模型设置」中配置；服务始终走真实模型运行时
```

浏览器打开 `http://127.0.0.1:8000/`（服务只绑定回环地址，R5/ADR-10）。

## 布局

```
┌──────────────────────────────────────────────────────────────────┐
│ SolveX ● 运行中 │ 模型 / Thinking 档 │ 输入·输出 token / ¥ │ [中止][模型⚙] │  ← 顶部实时用量条
├───────────┬──────────────────────────────────┬───────────────────┤
│ 左：会话  │ 中：标签页                        │ 右：阶段 DAG 时间线│
│ 历史列表  │ [阶段视图][思考过程][产物][日志]  │ P1 ● 完成          │
│ + 新建    │                                  │ P2 ◐ 3/5 并行      │
│           │                                  │ ├ model_1 ✓        │
│           │                                  │ ├ model_2 ◐ 思考   │
│           │                                  │ └ 屏障 3/5         │
├───────────┴──────────────────────────────────┴───────────────────┤
│ 底部：问题输入 + 数据拖拽上传 + 并行度滑块(1..N) + 严格模式 + [开始] │
└──────────────────────────────────────────────────────────────────┘
```

## 三视图

### 1. 模型配置中心（⚙）
- 按 provider 分组、搜索、能力标签（reasoning / vision / 上下文 / 单价）。
- 每个模型可「设为默认」「加入循环集」「分配到阶段」（P1/P2_IMPL/P2_REVIEW/P3/P4）。
- thinking 档位按模型能力过滤：不支持 reasoning 自动降为 `off`。
- 凭据面板：环境变量只读（遮蔽）、运行时注入 Key（**只进内存**）、自定义 OpenAI 兼容端点（`apiKey` 支持 `$VAR` / `${VAR}` 插值，写出的 `models` 为 SDK 合规对象数组）。
- 保存即刷新；`GET /api/models` 响应体**不含任何明文密钥**，只回 `masked`。

### 2. 思考过程
- 数据来自 Pi 原生 `thinking_start/_delta/_end`（带 `contentIndex`），按 `blockId` 流式重建。
- `*_end.content` 是权威值，覆盖增量拼接；`message_end` 覆盖整个 partial 消息。
- 默认折叠，摘要行显示字数/思考时长，点击展开；全局「隐藏思考」开关。
- `redacted` 显示「该模型的思考内容不可见」；单块 >64KB 截断标记。
- 并行任务按 `taskId` 分栏，互不混淆。**思考正文与产物严格隔离**，默认不落盘。

### 3. 运行阶段
- 双层：外层 `stage`/`barrier` 由编排层权威发出（Pi 不知道四阶段语义），内层 `turn`/`tool`/`thinking`/`output` 由 `eventBridge` 转发，靠 `taskId` 关联。
- 并行节点独立刷新，屏障显示 `3/5`，失败标红但不阻塞兄弟，可展开查看该会话的 turn / 工具 / 思考 / 输出。
- **只有 `complete` 才把运行标为完成**；`agent_end` 只是生命周期信号（自动重试期间不误判）。

## 交互流程
1. 底部输入问题文本、拖拽 CSV/XLSX/ZIP 数据文件，设置并行度与严格模式，点「开始」。
2. 前端用 `FormData` 提交 `POST /api/run`（不手动设置 `Content-Type`，修复旧版 multipart bug），返回 `session_id`。
3. 先拉 `GET /api/events/{id}?since=N` + `GET /api/stages/{id}` 回放历史，再接 `GET /api/stream/{id}` SSE。
4. 断线自动用 `Last-Event-ID` 续传；刷新页面不丢思考与阶段。
5. 完成后在「产物」标签查看真实文件树、点击预览文本、`GET /api/download/{id}` 下载 ZIP。
6. 需要中止时点「中止」（`POST /api/abort/{id}`），一次取消所有在跑并行任务。

## 端点（14 个）
`/api/run`、`/api/stream/{id}`、`/api/download/{id}`、`/api/sessions`（旧 4 个，保持兼容）+
`/api/artifacts/{id}`、`/api/events/{id}`、`/api/stages/{id}`、`/api/abort/{id}`、
`/api/models`、`/api/models/config`、`/api/models/refresh`、`/api/models/api-key`、
`/api/models/endpoints`、`/api/models/thinking-levels`（新增 10 个）。
另有 `/api/artifacts/{id}/{path}` 供文件树点击预览。

## 技术
原生 ES modules，无构建链：`public/{index.html,styles.css,app.js}` + `modules/{store,stream,models,thinking,stages,artifacts}.js`。
单一 `SessionStore` 用纯函数 `reduce(state, event)` 更新，配 `test/web/*.test.ts`（66 个纯函数测试），不依赖 DOM。
