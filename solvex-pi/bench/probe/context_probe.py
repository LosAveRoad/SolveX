#!/usr/bin/env python3
"""上下文退化探针：直接经 mistral-gateway 调 GLM 5.3 Flash，三组实验。

E1 真实会话重放：取 r6 Model 3 实现会话（修复失败处约 174K token），截到不同长度后发同一条
   fix-1 修复意见，看第一轮是「调工具动手」「只说不做」还是「空回复」，以及工具参数里的路径是否正确。
E2 大海捞针：真实工具输出拼成 64K–500K 的上下文，埋 5 条事实，看能否取回（验证 500K 是否可用）。
E3 中文路径：短上下文下让模型对 15 个文件拼绝对路径调 read，对比工作区路径含中文 / 纯 ASCII。

用法：python3 bench/probe/context_probe.py [e1] [e2] [e3]   （默认全部）
结果：bench/results/context-probe/<实验>.json
"""
import json, os, random, re, sys, time, glob, urllib.request, concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GW = os.environ.get("MISTRAL_GW_URL", "http://127.0.0.1:8788") + "/v1/chat/completions"
MODEL = "zai-glm-5-3-flash"
RUN = os.path.join(ROOT, "bench/sessions/r6-c3-quality-mwojr1zz")
WS = RUN                                                     # r6 会话 cwd（含中文）
OUT = os.path.join(ROOT, "bench/results/context-probe")
os.makedirs(OUT, exist_ok=True)
CHARS_PER_TOKEN = 3.3                                        # 估算用；报告里用接口返回的 prompt_tokens


def chat(messages, tools=None, effort="max", max_tokens=32768, timeout=1500):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "stream": False,
            "reasoning_effort": effort}
    if tools: body["tools"] = tools
    req = urllib.request.Request(GW, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer local"})
    t0 = time.time()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
            j["_secs"] = round(time.time() - t0, 1)
            return j
        except Exception as e:                                # 上游中断：退避重试
            err = str(e)
            if hasattr(e, "read"):
                try: err += " " + e.read().decode()[:300]
                except Exception: pass
            if attempt == 3: return {"_error": err, "_secs": round(time.time() - t0, 1)}
            time.sleep(15 * (attempt + 1))


# ---------- Pi 会话日志 → OpenAI 消息 ----------
def text_of(content):
    if isinstance(content, str): return content
    return "".join(c.get("text", "") for c in content if c.get("type") == "text")


def load_session(path):
    es = [json.loads(l) for l in open(path)]
    sysm = next(e["message"] for e in es if e.get("type") == "message" and e["message"]["role"] == "system")
    system = "\n\n".join(v for v in sysm["sections"].values() if isinstance(v, str))
    tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("parameters", {"type": "object"})}}
             for t in sysm["toolsAdded"]]
    msgs, call = [], None                                     # (call 名, openai 消息)
    for e in es:
        if e.get("type") == "custom" and e.get("customType") == "solvex_call": call = e["data"]["call"]
        if e.get("type") != "message": continue
        m = e["message"]
        if m["role"] == "user":
            msgs.append((call, {"role": "user", "content": text_of(m["content"])}))
        elif m["role"] == "assistant":
            if m.get("stopReason") in ("error", "aborted"): continue
            tcs = [c for c in m["content"] if c.get("type") == "toolCall"]
            o = {"role": "assistant", "content": text_of(m["content"]) or None}
            th = "".join(c.get("thinking", "") for c in m["content"] if c.get("type") == "thinking")
            if th: o["reasoning_content"] = th
            if tcs:
                o["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                    "name": c["name"], "arguments": json.dumps(c.get("arguments", {}), ensure_ascii=False)}} for c in tcs]
            msgs.append((call, o))
        elif m["role"] == "toolResult":
            msgs.append((call, {"role": "tool", "tool_call_id": m["toolCallId"], "content": text_of(m["content"])}))
    # 去掉没有对应 tool 结果的 tool_calls（出错重试留下的孤立调用），与 Pi 重建上下文的修补一致
    have = {o["tool_call_id"] for _, o in msgs if o["role"] == "tool"}
    for _, o in msgs:
        if o.get("tool_calls"):
            o["tool_calls"] = [t for t in o["tool_calls"] if t["id"] in have] or None
            if not o["tool_calls"]: o.pop("tool_calls")
    ids = {t["id"] for _, o in msgs for t in (o.get("tool_calls") or [])}
    msgs = [(c, o) for c, o in msgs if o["role"] != "tool" or o["tool_call_id"] in ids]
    return system, tools, msgs


def size(o):
    """估算计入上下文的字符数。历史 assistant 的 reasoning_content 会随请求发出（与 Pi 一致），
    但 r6 实测上游不把它计入 prompt（1.1M 字符 thinking，实计只有 174K token），估算时排除。"""
    return len(json.dumps({k: v for k, v in o.items() if k != "reasoning_content"}, ensure_ascii=False))


def truncate(system, history, target_tokens):
    """保留首条任务消息 + 末尾若干条历史，使总长约为 target_tokens；切点落在 user/assistant 上，不拆 tool 对。"""
    first, rest = history[0], history[1:]
    budget = target_tokens * CHARS_PER_TOKEN - len(system) - size(first)
    keep, total = [], 0
    for o in reversed(rest):
        total += size(o)
        keep.append(o)
        if total >= budget: break
    keep.reverse()
    while keep and keep[0]["role"] == "tool": keep.pop(0)
    note = {"role": "user", "content": "[earlier turns of this session omitted for length]"} if len(keep) < len(rest) else None
    out = [first] + ([note, {"role": "assistant", "content": "Understood, continuing."}] if note else []) + keep
    return out


PATH_RE = re.compile(r"/Users/[^\s\"'`\\;|&)]*")


def path_check(args_text, ws):
    paths = PATH_RE.findall(args_text)
    bad = [p for p in paths if not (p.startswith(ws) or ws.startswith(p.rstrip("/")))]
    return len(paths), bad


def classify(resp, ws):
    if "_error" in resp: return {"outcome": "error", "error": resp["_error"][:200], "secs": resp["_secs"]}
    ch = resp["choices"][0]; msg = ch["message"]; u = resp.get("usage", {})
    tcs = msg.get("tool_calls") or []
    text = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    n, bad = path_check(" ".join(t["function"]["arguments"] for t in tcs), ws)
    outcome = ("tool_call_bad_path" if bad else "tool_call") if tcs else ("text_only" if text.strip() else "empty")
    return {"outcome": outcome, "finish": ch.get("finish_reason"), "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"), "n_tool_calls": len(tcs), "paths": n, "bad_paths": bad[:5],
            "tools": [t["function"]["name"] for t in tcs], "text": text[:200], "reasoning_chars": len(reasoning),
            "secs": resp["_secs"]}


def run_parallel(jobs, workers=4):
    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: j(), jobs))


# ---------- E1 ----------
def e1():
    system, tools, msgs = load_session(os.path.join(RUN, ".solvex/journal/P2-IMPL_model_3.jsonl"))
    idx = next(i for i, (c, o) in enumerate(msgs) if c == "fix-1" and o["role"] == "user")
    history = [o for _, o in msgs[:idx]]
    fix = msgs[idx][1]
    full_est = (len(system) + sum(size(o) for o in history)) / CHARS_PER_TOKEN
    lengths = [32_000, 64_000, 100_000, 140_000, None]        # None = 完整历史（r6 实际 ~174K）
    jobs, meta = [], []
    for L in lengths:
        conv = history if L is None else truncate(system, history, L)
        messages = [{"role": "system", "content": system}] + conv + [fix]
        for effort in ("max", "high"):
            for rep in range(3):
                meta.append({"target": L or "full", "effort": effort, "rep": rep})
                jobs.append(lambda m=messages, e=effort: classify(chat(m, tools, e), WS))
    print(f"E1: {len(jobs)} requests, full history ≈ {full_est/1000:.0f}K tokens (est.)", flush=True)
    res = run_parallel(jobs)
    rows = [{**m, **r} for m, r in zip(meta, res)]
    json.dump(rows, open(os.path.join(OUT, "e1.json"), "w"), ensure_ascii=False, indent=1)
    return rows


# ---------- E2 ----------
def haystack_text():
    parts = []
    for fn in sorted(glob.glob(os.path.join(RUN, ".solvex/journal/*.jsonl"))):
        for l in open(fn):
            e = json.loads(l)
            if e.get("type") == "message" and e["message"]["role"] == "toolResult":
                t = text_of(e["message"]["content"])
                if len(t) > 200: parts.append(t)
    return parts


def e2():
    random.seed(7)
    parts = haystack_text()
    names = ["Aurora", "Basalt", "Cobalt", "Dune", "Ember"]
    lengths = [64_000, 128_000, 256_000, 384_000, 500_000]
    jobs, meta = [], []
    for L in lengths:
        target_chars = int(L * CHARS_PER_TOKEN)
        chunks, total, i = [], 0, 0
        while total < target_chars:
            p = parts[i % len(parts)][:6000]; i += 1
            chunks.append(p); total += len(p)
        facts = {n: str(random.randint(100000, 999999)) for n in names}
        for k, n in enumerate(names):                          # 深度 10/30/50/70/90%
            pos = int(len(chunks) * (0.1 + 0.2 * k))
            chunks.insert(pos, f"\n[AUDIT NOTE] The calibration constant for {n} is {facts[n]}.\n")
        ctx = "\n\n---\n\n".join(chunks)
        q = ("Above is a long log of tool outputs. Somewhere in it are five lines starting with [AUDIT NOTE]. "
             "Reply with exactly five lines in the form `Name: number` for Aurora, Basalt, Cobalt, Dune, Ember, "
             "copying the numbers exactly. If you cannot find one, write `Name: NOT FOUND`.")
        messages = [{"role": "user", "content": ctx + "\n\n" + q}]
        meta.append({"target": L, "facts": facts})
        jobs.append(lambda m=messages: chat(m, None, "high", max_tokens=8192, timeout=2400))
    print(f"E2: {len(jobs)} requests up to {lengths[-1]//1000}K", flush=True)
    res = run_parallel(jobs, workers=2)
    rows = []
    for m, r in zip(meta, res):
        if "_error" in r:
            rows.append({"target": m["target"], "error": r["_error"][:300], "secs": r["_secs"]}); continue
        text = r["choices"][0]["message"].get("content") or ""
        got = sum(1 for n, v in m["facts"].items() if re.search(rf"{n}\W+{v}\b", text))
        rows.append({"target": m["target"], "prompt_tokens": r.get("usage", {}).get("prompt_tokens"),
                     "recall": f"{got}/5", "answer": text[:300], "secs": r["_secs"]})
    json.dump(rows, open(os.path.join(OUT, "e2.json"), "w"), ensure_ascii=False, indent=1)
    return rows


# ---------- E3 ----------
FILES = ["01_modeling/master_plan.md", "01_modeling/shared_data/data_dictionary.md", "01_modeling/shared_data/checks.md",
         "02_programming/model_1/run.py", "02_programming/model_1/results.json", "02_programming/model_1/results_summary.md",
         "02_programming/model_2/run.py", "02_programming/model_2/results.json", "02_programming/model_2/model2_core.py",
         "02_programming/model_3/run.py", "02_programming/model_3/m3_lab.py", "02_programming/model_3/m3_core.py",
         "02_programming/model_3/outputs/model3_controversies.csv", "04_paper/main.tex", "00_problem/problem.md"]


def e3():
    _, tools, _ = load_session(os.path.join(RUN, ".solvex/journal/P2-IMPL_model_3.jsonl"))
    read_tool = [t for t in tools if t["function"]["name"] == "read"]
    variants = {"cjk": WS, "ascii": WS.replace("/学习/找工作/", "/study/jobs/")}
    jobs, meta = [], []
    for name, ws in variants.items():
        system = (f"You are an autonomous coding agent. Your workspace (current working directory) is:\n{ws}\n"
                  "Tool calls must use ABSOLUTE paths under the workspace.")
        user = ("Before revising the paper, open every file below. Call the read tool once per file, all in this turn, "
                "with its absolute path:\n" + "\n".join(f"- {f}" for f in FILES))
        for rep in range(4):
            meta.append({"variant": name, "rep": rep, "ws": ws})
            jobs.append(lambda s=system, u=user, w=ws: classify(chat([{"role": "system", "content": s},
                                                                      {"role": "user", "content": u}], read_tool, "max"), w))
    print(f"E3: {len(jobs)} requests", flush=True)
    res = run_parallel(jobs)
    rows = [{**m, **r} for m, r in zip(meta, res)]
    json.dump(rows, open(os.path.join(OUT, "e3.json"), "w"), ensure_ascii=False, indent=1)
    return rows


if __name__ == "__main__":
    which = sys.argv[1:] or ["e3", "e1", "e2"]
    for w in which:
        rows = {"e1": e1, "e2": e2, "e3": e3}[w]()
        for r in rows: print(w, json.dumps({k: v for k, v in r.items() if k not in ("text", "answer", "facts", "ws")}, ensure_ascii=False), flush=True)
