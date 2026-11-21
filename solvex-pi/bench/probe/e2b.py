"""E2 加测：384K 目标（实际约 450K）再跑 2 次，确认 r1 的 0/5 是否偶发。"""
import sys, os, json, re, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import context_probe as P
parts = P.haystack_text(); names = ["Aurora", "Basalt", "Cobalt", "Dune", "Ember"]
rows = []
def one(seed):
    random.seed(seed)
    target = int(384_000 * P.CHARS_PER_TOKEN); chunks, total, i = [], 0, seed
    while total < target:
        p = parts[i % len(parts)][:6000]; i += 1; chunks.append(p); total += len(p)
    facts = {n: str(random.randint(100000, 999999)) for n in names}
    for k, n in enumerate(names):
        chunks.insert(int(len(chunks) * (0.1 + 0.2 * k)), f"\n[AUDIT NOTE] The calibration constant for {n} is {facts[n]}.\n")
    q = ("Above is a long log of tool outputs. Somewhere in it are five lines starting with [AUDIT NOTE]. Reply with exactly "
         "five lines in the form `Name: number` for Aurora, Basalt, Cobalt, Dune, Ember, copying the numbers exactly.")
    r = P.chat([{"role": "user", "content": "\n\n---\n\n".join(chunks) + "\n\n" + q}], None, "high", 8192, 2400)
    if "_error" in r: return {"seed": seed, "error": r["_error"][:200]}
    t = r["choices"][0]["message"].get("content") or ""
    return {"seed": seed, "prompt_tokens": r["usage"]["prompt_tokens"], "recall": sum(bool(re.search(rf"{n}\W+{v}\b", t)) for n, v in facts.items()), "answer": t[:120], "secs": r["_secs"]}
rows = P.run_parallel([lambda s=s: one(s) for s in (11, 23)], workers=2)
json.dump(rows, open(os.path.join(P.OUT, "e2b.json"), "w"), ensure_ascii=False, indent=1)
print(rows)
