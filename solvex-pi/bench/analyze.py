#!/usr/bin/env python3
"""汇总 bench/results/*/metrics.json，输出对比表（markdown）。

用法: python3 bench/analyze.py [label ...]
"""
import json
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent / "results"

WARN_PATTERNS = {
    "summary_retry": r"requesting a dedicated summary turn",
    "continue_nudge": r"stopped before finishing",
    "summary_autogen": r"generated evidence-based summary",
    "plan_retry": r"Master Plan not saved",
    "plan_restored": r"Restored master_plan.md",
    "validation_issue": r"validation issue",
    "tool_failed": r"^tool .* failed",
}


def load(labels):
    paths = [ROOT / l / "metrics.json" for l in labels] if labels else sorted(ROOT.glob("*/metrics.json"))
    return [json.loads(p.read_text()) for p in paths if p.exists()]


def s(ms):
    return f"{ms / 1000:.0f}s" if ms else "-"


def row(m):
    st = m["stagesMs"]
    par = m["parallel"]
    tok = m["tokens"]
    gw = tok.get("gateway") or {}
    gw_total = (gw.get("prompt_tokens", 0) + gw.get("completion_tokens", 0)) if gw else None
    fm = tok["finalMessages"]
    fm_total = fm["input"] + fm["output"]
    rep = tok["solvexReported"]["total"]
    calls = sum(t["calls"] for t in m["tools"].values())
    errs = sum(t["errors"] for t in m["tools"].values())
    warns = Counter()
    for w in m["warns"]:
        for k, pat in WARN_PATTERNS.items():
            if re.search(pat, w["message"]):
                warns[k] += 1
    issues = Counter(i["code"] for i in (m.get("issues") or []))
    wc = m.get("writeClasses", {})
    bad_writes = sum(v for k, v in wc.items() if k != "ok")
    blocked = sum(1 for w in m["writes"] if w["cls"] != "ok" and w.get("blocked"))
    return {
        "label": m["label"], "status": m["status"], "conc": m["concurrency"],
        "wall": s(m["wallMs"]), "P1": s(st.get("P1", 0)),
        "impl wall/sum": f'{s(par["implWallMs"])}/{s(par["implSumMs"])}',
        "impl×": par["implSpeedup"], "review×": par["reviewSpeedup"],
        "P4": s(st.get("P4", 0)),
        "tok reported": rep, "tok msgs": fm_total, "tok gateway": gw_total,
        "inflation": f"{rep / gw_total:.1f}x" if rep and gw_total else "-",
        "gw reqs": gw.get("requests"), "cache hit": f'{gw["cached_tokens"] / gw["prompt_tokens"]:.0%}' if gw.get("prompt_tokens") else "-",
        "tool calls": calls, "tool errs": errs,
        "writes bad/total": f"{bad_writes}/{len(m['writes'])}", "bad blocked": blocked,
        "warns": dict(warns), "issues": dict(issues),
        "compaction": m["lifecycle"].get("compaction:compaction_start", 0),
        "retries": m["lifecycle"].get("auto_retry:auto_retry_start", 0),
        "paper": m["paper"]["bytes"],
        **artifacts(m["sessionDir"]),
        **reviews(m["label"]),
    }


def reviews(label):
    """评审结论可用率：评审 Agent 最终输出里是否给出 VERIFICATION_RESULT，以及编排层是否接住并触发修复。"""
    ev = [json.loads(l) for l in (ROOT / label / "events.jsonl").open()]
    last = {}
    for e in ev:
        if e["type"] == "output" and e.get("state") == "end" and str(e.get("taskId", "")).startswith("P2-REVIEW"):
            last[e["taskId"]] = e.get("content") or ""
    m = json.loads((ROOT / label / "metrics.json").read_text())
    # 定向修复与评审共用 taskId，最后一条输出可能来自修复 Agent：有落盘评审文件时以文件为准。
    modeling = pathlib.Path(m["sessionDir"]) / "01_modeling"
    for f in modeling.glob("model_*_review.md"):
        last[f"P2-REVIEW:{f.name[:-len('_review.md')]}"] = f.read_text(errors="ignore")
    given = Counter()
    for t in last.values():
        mm = re.findall(r"VERIFICATION_RESULT:\s*(SATISFIED|NEEDS_REVISION)", t, re.I)
        given[mm[-1].upper() if mm else "NONE"] += 1
    captured = Counter((x.get("verdict") or "unknown") for x in (m.get("models") or []))
    fixes = sum(1 for e in ev if e["type"] in ("done", "warn") and re.search(r"Targeted revision applied|targeted revision round \d+ hit", e.get("message") or ""))
    rounds = [x.get("reviewRounds") for x in (m.get("models") or []) if x.get("reviewRounds")]
    msgs = [(e["type"], e.get("message") or "") for e in ev]
    repro_ok = sum(1 for t, x in msgs if t == "done" and "reproduction passed" in x)
    repro_fail = sum(1 for t, x in msgs if t == "warn" and re.search(r"reproduction failed \(", x))
    repro_gaveup = sum(1 for t, x in msgs if t == "warn" and "reproduction failed after" in x)
    reverted = sum(1 for t, x in msgs if t == "warn" and re.search(r"Reverted changes made during review|Phase-1 artifacts are read-only", x))
    return {"review verdicts given": dict(given), "verdicts captured": dict(captured), "targeted fixes": fixes,
            "review rounds": rounds or "-",
            "repro pass/fail/gave-up": f"{repro_ok}/{repro_fail}/{repro_gaveup}", "guard reverts": reverted,
            "shared data": "yes" if (pathlib.Path(m["sessionDir"]) / "01_modeling" / "shared_data" / "data_dictionary.md").exists() else "no"}


def artifacts(session_dir):
    """事后扫描会话目录：几个模型真正产出了代码 / 图 / Agent 自写摘要。"""
    prog = pathlib.Path(session_dir) / "02_programming"
    dirs = [d for d in prog.iterdir() if d.is_dir()] if prog.exists() else []
    code = sum(1 for d in dirs if any(d.rglob("*.py")))
    figs = sum(1 for d in dirs if any(p.suffix.lower() in {".png", ".pdf", ".svg", ".jpg"} for p in d.rglob("*")))
    own_summary = sum(1 for d in dirs if (d / "results_summary.md").exists()
                      and "auto-generated from workspace scan" not in (d / "results_summary.md").read_text(errors="ignore"))
    n = len(dirs)
    return {"models w/ code": f"{code}/{n}", "w/ figures": f"{figs}/{n}", "agent summary": f"{own_summary}/{n}"}


def main():
    rows = [row(m) for m in load(sys.argv[1:])]
    if not rows:
        print("no metrics found")
        return
    keys = list(rows[0].keys())
    print("| " + " | ".join(keys) + " |")
    print("|" + "---|" * len(keys))
    for r in rows:
        print("| " + " | ".join(str(r[k]) for k in keys) + " |")


if __name__ == "__main__":
    main()
