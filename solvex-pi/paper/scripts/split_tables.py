"""Split the auto-generated table bundles into one file per LaTeX label."""
import os
import re

OUT = "/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/sessions/rerun-2026-mcmc/04_paper/chapters"
blocks = []
for src in ["tables_gen.tex", "tables_extra.tex"]:
    text = open(os.path.join(OUT, src), encoding="utf-8").read()
    for m in re.finditer(
            r"(\\begin\{table\}\[H\][\s\S]*?\\end\{table\}|"
            r"\\begin\{longtable\}[\s\S]*?\\end\{longtable\})", text):
        block = m.group(1)
        lab = re.search(r"\\label\{([^}]+)\}", block)
        if not lab:
            continue
        name = "tab_" + lab.group(1).split(":")[-1] + ".tex"
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write("% AUTO-GENERATED table — values computed by analyze_extended.py\n"
                     + block + "\n")
        blocks.append((name, len(block.splitlines())))
for n, l in blocks:
    print(n, l, "lines")
print("total", len(blocks), "tables")
