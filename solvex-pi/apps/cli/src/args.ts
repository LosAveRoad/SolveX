export type Command = "run" | "serve" | "inspect" | "validate" | "help";
export type CliArgs = {
  command: Command;
  problem?: string;
  data: string[];
  resume?: string;
  fromModel?: number;
  skipToWriting: boolean;
  sessionDir?: string;
  strict: boolean;
  concurrency: number;
  port: number;
  sessionId?: string;
  interactive: boolean;
  help: boolean;
};

export const HELP = `SolveX — 多模型数学建模流水线（Pi SDK 编排）

用法:
  solvex run [选项]              运行完整四阶段流水线
  solvex serve [--port N]        启动 WebUI 2.0（默认 127.0.0.1:8000）
  solvex inspect <session_id>    查看某次运行的阶段与产物
  solvex validate <session_id>   重跑质量门（不修改任何产物）

run 选项（与旧版 1:1 兼容）:
  -p, --problem FILE             问题文本 .md/.txt
  -d, --data PATH                数据文件/目录（可重复）
  -r, --resume ID                续跑 session，跳过已完成的模型
      --from-model N             从第 N 个模型续跑
  -w, --skip-to-writing          仅执行 P3 聚合 + P4 写作
      --session-dir DIR          覆盖 ~/.solvex/sessions
      --concurrency N            并行上限（默认 3；=1 等价旧版串行）
      --strict                   Critical 问题阻断进入 P4
  -h, --help                     显示帮助

运行前需在 WebUI 的「模型设置」中配置至少一个可用的模型 provider 凭据。
无参数运行 solvex run 时进入交互式问题输入。
`;

/** 手写解析，保持与旧 run_flow.py 参数一一对应。 */
export function parseArgs(argv: string[]): CliArgs {
  const a: CliArgs = { command: "run", data: [], skipToWriting: false, strict: false,
    concurrency: 3, port: 8000, interactive: false, help: false };
  const rest = [...argv];
  const cmds: Command[] = ["run", "serve", "inspect", "validate"];
  if (rest.length && cmds.includes(rest[0] as Command)) a.command = rest.shift() as Command;

  for (let i = 0; i < rest.length; i++) {
    const x = rest[i];
    switch (x) {
      case "-h": case "--help": a.help = true; break;
      case "-p": case "--problem": a.problem = rest[++i]; break;
      case "-d": case "--data": a.data.push(rest[++i]); break;
      case "-r": case "--resume": a.resume = rest[++i]; break;
      case "--from-model": a.fromModel = Number(rest[++i]); break;
      case "-w": case "--skip-to-writing": a.skipToWriting = true; break;
      case "--session-dir": a.sessionDir = rest[++i]; break;
      case "--strict": a.strict = true; break;
      case "--concurrency": a.concurrency = Math.max(1, Number(rest[++i]) || 3); break;
      case "--port": a.port = Number(rest[++i]) || 8000; break;
      default:
        // 明确拒绝未知选项，避免旧版演示开关被静默忽略后误入真实模型调用。
        if (x.startsWith("-")) throw new Error(`未知选项: ${x}`);
        if (!x.startsWith("-") && (a.command === "inspect" || a.command === "validate") && !a.sessionId)
          a.sessionId = x;
    }
  }
  if (a.command === "run" && !a.problem && !a.resume && !a.help) a.interactive = true;
  return a;
}
