"""E1 加测：关键格子（完整 177K × max/high、126K × max）各 6 次。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import context_probe as P
system, tools, msgs = P.load_session(os.path.join(P.RUN, ".solvex/journal/P2-IMPL_model_3.jsonl"))
idx = next(i for i, (c, o) in enumerate(msgs) if c == "fix-1" and o["role"] == "user")
history = [o for _, o in msgs[:idx]]; fix = msgs[idx][1]
jobs, meta = [], []
for L, effort in [(None, "max"), (None, "high"), (140_000, "max")]:
    conv = history if L is None else P.truncate(system, history, L)
    m = [{"role": "system", "content": system}] + conv + [fix]
    for rep in range(6):
        meta.append({"target": L or "full", "effort": effort, "rep": rep})
        jobs.append(lambda m=m, e=effort: P.classify(P.chat(m, tools, e), P.WS))
rows = [{**a, **b} for a, b in zip(meta, P.run_parallel(jobs, workers=4))]
json.dump(rows, open(os.path.join(P.OUT, "e1b.json"), "w"), ensure_ascii=False, indent=1)
for r in rows: print(json.dumps({k: v for k, v in r.items() if k != "text"}, ensure_ascii=False), flush=True)
