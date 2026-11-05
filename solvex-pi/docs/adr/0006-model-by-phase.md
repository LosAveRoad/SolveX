# ADR-0006：默认模型不硬编码 + 按阶段分档 + thinking 档位裁剪（D5）

- 状态：已接受（2026-11-05）
- ① 默认模型由 `models.json` + 凭据探测决定，不写死在代码里；无凭据时 WebUI 引导配置，golden 回归固定模型以隔离变量。
- ② 按阶段分档：`byPhase` 覆盖 P1（强推理 + `high`）、P2_IMPL（性价比 + `medium`）、P2_REVIEW（强推理 + `high`）、P3（`off`，纯代码不调模型）、P4（长上下文）。落到 `createAgentSession({ model, thinkingLevel, scopedModels, modelRuntime })`。
- ③ 7 档 thinking（`off|minimal|low|medium|high|xhigh|max`）按模型 `reasoning` 能力裁剪；`Usage.reasoning` 是 `output` 子集，**绝不重复计成本**。
- 实现：`packages/pi-runtime/src/{modelRuntime.ts, config.ts}`、`apps/web/src/modelConfig.ts`。
- 注意：Pi 1.5.0 的 `model` 参数是 `Model` 对象（由 `ModelRuntime.getModel()` 解析），`scopedModels` 是 `{model, thinkingLevel}[]` —— 与设计文档初稿的 `{provider,id}` / `string[]` 不同，已在适配层转换（见 ADR-0001 的实测记录）。
