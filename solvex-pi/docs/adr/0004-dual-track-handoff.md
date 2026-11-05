# ADR-0004：结构化 handoff 采用双轨兼容（D3 推荐方案 C）

- 状态：已接受（2026-11-05）
- 背景：旧版靠自然语言里的 `VERIFICATION_RESULT` / `## Model N:` 标记，B2/E4/C1/D4 等问题都源于此。纯结构化会令旧 session 无法 resume 且需改写 5 段内联提示词（违反逐字搬运硬约束）。
- 决策：优先读 `handoff.json`（TypeBox-like schema：`{status, issues[], fixInstructions, summaryPath}`），读不到回退正则解析旧标记；两者冲突时以结构化为准并记 `warn`。提示词只**追加一句** `HANDOFF_HINT`（增强非改写），5 段内联模板与 7 个 `.md` 保持逐字。
- 实现：`packages/core/src/contracts/handoff.ts`、`gates/parseVerdict.ts`、`prompts/inline/template.ts`。
- 验证：`test/gates/parseVerdict.test.ts`（5 条）+ `test/regression/legacy-issues.test.ts` 的「无 handoff.json 的旧 session 仍能完成」。
