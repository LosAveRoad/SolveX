# ADR-0007：凭据脱敏与隐私边界（R13 / ADR-13）

- 状态：已接受（2026-11-05）
- `models.json` 的 `apiKey` 只允许环境变量引用（Pi SDK 1.5.0 语法 `$VAR` / `${VAR}`，旧写法 `$ENV:VAR` 兼容转换；`validateModelCatalog` 强制校验）；`GET /api/models` 响应体不含 `apiKey` 字段，凭据只回 `masked: "sk-••••1234"`。
- `POST /api/models/api-key` 的 Key **只进内存**（`ModelRuntimeManager.setRuntimeApiKey`），不写 `config.json`、不进日志、不进 `events.jsonl`。
- thinking 正文默认只在内存与 SSE 流转（`persistThinking: false`），`events.jsonl` 剥离 `delta`/`content`；导出 ZIP 不含思考记录。
- 服务只绑定 `127.0.0.1`；`tool_call` 拦截 `..` 路径逃逸与 `writablePrefixes` 越界写入（R5/R11）。
- 验证：`test/web/api.test.ts` 的脱敏断言、`test/pi/modelRuntime.test.ts`、`test/pi/extensions.test.ts`。
