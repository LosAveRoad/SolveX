import { existsSync, readFileSync, writeFileSync, chmodSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** 本地凭据文件名与显式覆盖变量（自定义部署 / 测试用）。 */
export const ENV_FILE_NAME = ".env";
export const ENV_FILE_OVERRIDE = "SOLVEX_ENV_FILE";

/** 从本模块位置向上定位仓库根，保证从任意 cwd 启动都能找到同一份 .env。 */
function repoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (;;) {
    if (existsSync(join(dir, "pnpm-workspace.yaml"))) return dir;
    const parent = dirname(dir);
    if (parent === dir) return process.cwd();
    dir = parent;
  }
}

/**
 * 定位 .env：SOLVEX_ENV_FILE > 当前工作目录 > 仓库根。
 * 只做路径解析，不读取内容，更不会把任何值写进日志。
 */
export function findSolvexEnv(opts: { cwd?: string } = {}): string | undefined {
  const override = process.env[ENV_FILE_OVERRIDE];
  if (override) {
    const p = resolve(override);
    return existsSync(p) ? p : undefined;
  }
  for (const dir of [resolve(opts.cwd ?? process.cwd()), repoRoot()]) {
    const p = join(dir, ENV_FILE_NAME);
    if (existsSync(p)) return p;
  }
  return undefined;
}

/**
 * 幂等加载本地 .env（Node 22 原生 process.loadEnvFile，零新增依赖）。
 *
 * - 已在 shell 里 export 的同名变量优先，.env 不会覆盖它；
 * - 文件缺失、格式错误或运行时不支持时静默跳过，绝不阻断 CLI / WebUI 启动；
 * - 配置文件里的 apiKey 仍只允许 $VAR / ${VAR} 引用，接口只回 masked。
 */
export function loadSolvexEnv(opts: { cwd?: string } = {}): string | undefined {
  const path = findSolvexEnv(opts);
  if (!path) return undefined;
  const loader = (process as any).loadEnvFile as ((file: string) => void) | undefined;
  if (typeof loader !== "function") return undefined;
  try {
    loader.call(process, path);
    return path;
  } catch {
    return undefined;
  }
}

/** 写入目标：SOLVEX_ENV_FILE > 已存在的 .env > 仓库根 .env（不存在时创建）。 */
export function envFileTarget(opts: { cwd?: string } = {}): string {
  const override = process.env[ENV_FILE_OVERRIDE];
  if (override) return resolve(override);
  return findSolvexEnv(opts) ?? join(repoRoot(), ENV_FILE_NAME);
}

/** 含空格、#、引号、等号或反斜杠的值加引号，保证 Node 的 env-file 解析不截断。 */
function quoteEnvValue(value: string): string {
  if (!/[\s#"'=\\]/.test(value)) return value;
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/**
 * 把凭据显式写进 .env：保留注释与其它变量、替换同名占位行、权限 600，
 * 并让当前进程立即拿到该值。调用方负责确保这是用户的明确选择；
 * 返回值只含路径与变量名，绝不回显明文。
 */
export function persistEnvVar(name: string, value: string, opts: { cwd?: string } = {}):
    { path: string; envVar: string } {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new Error("非法的环境变量名");
  if (!value || /[\r\n]/.test(value)) throw new Error("API Key 不能为空或包含换行");
  const path = envFileTarget(opts);
  const lines = existsSync(path) ? readFileSync(path, "utf-8").split(/\r?\n/) : [];
  // 同时命中未注释的赋值行与 `# NAME=` 形式的模板占位行。
  const re = new RegExp(`^\\s*#?\\s*${name}\\s*=`);
  const line = `${name}=${quoteEnvValue(value)}`;
  const out: string[] = [];
  let replaced = false;
  for (const current of lines) {
    if (re.test(current)) {
      if (!replaced) { out.push(line); replaced = true; }
      continue; // 丢弃重复定义
    }
    out.push(current);
  }
  if (!replaced) {
    while (out.length && out[out.length - 1].trim() === "") out.pop();
    out.push(line);
  }
  writeFileSync(path, out.join("\n").replace(/\n+$/, "") + "\n", { mode: 0o600 });
  try { chmodSync(path, 0o600); } catch { /* 个别文件系统不支持 chmod，忽略 */ }
  process.env[name] = value;
  return { path, envVar: name };
}
