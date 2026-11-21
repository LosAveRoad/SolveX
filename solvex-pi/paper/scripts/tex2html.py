import html
import re
import os

BASE = "/Users/mac/WorkBuddy/2026-11-05-11-28-19"
TEX = os.path.join(BASE, "tmp", "sessions", "mw323ika-oj43", "04_paper", "main.tex")
OUT = os.path.join(BASE, "tmp", "paper.html")

src = open(TEX, encoding="utf-8").read()
preamble, body = src.split("\\begin{document}", 1)
body = body.split("\\end{document}", 1)[0]

TOK = {
    "B": ("<strong>", "</strong>"),
    "I": ("<em>", "</em>"),
    "C": ("<code>", "</code>"),
}


def extract_cmd(s, name):
    pat = "\\" + name + "{"
    j = s.find(pat)
    if j < 0:
        return ""
    k = j + len(pat)
    depth, m = 1, k
    while m < len(s) and depth:
        if s[m] == "{":
            depth += 1
        elif s[m] == "}":
            depth -= 1
        m += 1
    return s[k : m - 1]


def replace_cmd(s, name, o, c):
    pat = "\\" + name + "{"
    out, i = [], 0
    while True:
        j = s.find(pat, i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        k = j + len(pat)
        depth, m = 1, k
        while m < len(s) and depth:
            if s[m] == "{":
                depth += 1
            elif s[m] == "}":
                depth -= 1
            m += 1
        out.append(o + s[k : m - 1] + c)
        i = m
    return "".join(out)


def inline(s):
    maths = []

    def stash(m):
        maths.append(m.group(1))
        return f"\x00M{len(maths)-1}\x00"

    s = re.sub(r"(?<!\\)\$([^$]+?)\$", stash, s)
    for lit, tok in [(r"\%", "PCT"), (r"\_", "US"), (r"\#", "HASH"), (r"\&", "AMP")]:
        s = s.replace(lit, f"\x00{tok}\x00")
    s = replace_cmd(s, "emph", "\x00I\x00", "\x00/I\x00")
    s = replace_cmd(s, "textbf", "\x00B\x00", "\x00/B\x00")
    s = replace_cmd(s, "texttt", "\x00C\x00", "\x00/C\x00")
    s = re.sub(r"\\(?:eqref|ref|label|cite)\{[^}]*\}", "(ref)", s)
    s = re.sub(r"\\paragraph\{([^}]*)\}", r"\1 ", s)
    s = s.replace("\\\\", " ").replace("~", "\u00a0").replace("--", "–")
    s = re.sub(r"\s+", " ", s).strip()
    s = html.escape(s, quote=False)
    for tok, (o, c) in TOK.items():
        s = s.replace(f"\x00{tok}\x00", o).replace(f"\x00/{tok}\x00", c)
    for lit, tok in [("%", "PCT"), ("_", "US"), ("#", "HASH"), ("&", "AMP")]:
        s = s.replace(f"\x00{tok}\x00", lit)
    for i, m in enumerate(maths):
        s = s.replace(f"\x00M{i}\x00", "\\(" + html.escape(m, quote=False) + "\\)")
    return s


def table_html(content, caption):
    content = re.sub(r"\\(?:toprule|midrule|bottomrule|centering)", "", content)
    content = re.sub(r"\\begin\{tabular\}\{[^}]*\}", "", content)
    content = re.sub(r"\\end\{tabular\}", "", content)
    rows = []
    for raw in content.split("\\\\"):
        cells = [inline(c.replace("\n", " ")) for c in raw.split("&")]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    head = "<tr>" + "".join(f"<th>{c}</th>" for c in rows[0]) + "</tr>"
    rest = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows[1:])
    return (f'<p class="caption">{inline(caption)}</p>'
            f'<table><thead>{head}</thead><tbody>{rest}</tbody></table>')


lines = body.split("\n")
out, toc = [], []
stack, buf, mathbuf, tablebuf, caption, bib = [], [], [], [], "", []
secno = 0


def flush():
    if buf:
        out.append("<p>" + inline(" ".join(buf)) + "</p>")
        buf.clear()


def close_list():
    if stack and stack[-1] in ("itemize", "enumerate"):
        out.append(f"</{stack[-1]}>")
        stack.pop()


for raw in lines:
    line = raw.strip()
    if line.startswith("%") and not line.startswith("\\%"):
        continue
    if not line:
        flush()
        continue
    m = re.match(r"\\begin\{([^}]+)\}", line)
    if m:
        env = m.group(1)
        flush()
        if env in ("itemize", "enumerate"):
            out.append(f"<{env}>")
            stack.append(env)
        elif env == "abstract":
            out.append('<div class="abstract"><h3>Abstract</h3>')
            stack.append(env)
        elif env in ("equation", "align", "equation*", "align*"):
            mathbuf = []
            stack.append(env)
        elif env in ("table", "table*"):
            tablebuf, caption = [], ""
            stack.append("table")
        elif env == "thebibliography":
            out.append("<ol class=\"refs\">")
            stack.append("bibliography")
        elif env == "tabular":
            pass
        continue
    m = re.match(r"\\end\{([^}]+)\}", line)
    if m:
        env = m.group(1)
        flush()
        if env in ("itemize", "enumerate") and stack and stack[-1] == env:
            out.append(f"</{env}>")
            stack.pop()
        elif env == "abstract":
            out.append("</div>")
            stack.pop()
        elif env in ("equation", "align", "equation*", "align*"):
            bodytex = "\n".join(mathbuf)
            if env.startswith("align"):
                bodytex = "\\begin{aligned}" + bodytex + "\\end{aligned}"
            out.append('<div class="math">\\[' + html.escape(bodytex, quote=False) + "\\]</div>")
            mathbuf = []
            stack.pop()
        elif env == "tabular":
            pass
        elif env in ("table", "table*"):
            out.append(table_html("\n".join(tablebuf), caption))
            tablebuf, caption = [], ""
            stack.pop()
        elif env == "thebibliography":
            out.append("</ol>")
            stack.pop()
        continue

    if stack and stack[-1] in ("equation", "align", "equation*", "align*"):
        mathbuf.append(line)
        continue
    if stack and stack[-1] == "table":
        cm = re.search(r"\\caption\{(.*)\}", line)
        if cm:
            caption = cm.group(1)
        elif line.startswith("\\begin{tabular}"):
            pass
        else:
            tablebuf.append(line.removeprefix("\\toprule").removeprefix("\\midrule"))
        continue
    if stack and stack[-1] == "bibliography":
        if line.startswith("\\bibitem"):
            out.append("<li>" + inline(line.split("}", 1)[-1]))
            bib.append(1)
        else:
            if out and out[-1].startswith("<li>"):
                out[-1] += " " + inline(line)
        continue

    m = re.match(r"\\(section|subsection|subsubsection)\*?\{(.*)\}", line)
    if m:
        flush()
        level, title = m.group(1), inline(m.group(2))
        secno += 1
        anchor = f"sec{secno}"
        tag = {"section": "h2", "subsection": "h3", "subsubsection": "h4"}[level]
        out.append(f'<{tag} id="{anchor}">{title}</{tag}>')
        if level in ("section", "subsection"):
            toc.append((level, anchor, title))
        continue
    if line.startswith("\\item"):
        flush()
        out.append("<li>" + inline(line[5:].strip()))
        continue
    if line.startswith("\\bibitem"):
        continue
    if line in ("\\maketitle", "\\newpage", "\\tableofcontents") or line.startswith("\\label"):
        continue
    if line.startswith("\\caption{"):
        caption = line[len("\\caption{"):-1]
        continue
    if line.startswith("\\centering") or line.startswith("\\toprule") or line.startswith("\\midrule") or line.startswith("\\bottomrule"):
        continue
    buf.append(line)

flush()

title = inline(extract_cmd(preamble, "title").replace("\\\\", " "))
author = inline(extract_cmd(preamble, "author").replace("\\\\", " · "))
date = inline(extract_cmd(preamble, "date"))

toc_html = "".join(
    f'<li class="{lv}"><a href="#{a}">{t}</a></li>' for lv, a, t in toc
)

CSS = """
:root{--ink:#1c1c1c;--muted:#5c625c;--line:#dfe3de;--accent:#3f6b52;--panel:#f6f8f5}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:17px/1.75 Georgia,'Times New Roman',serif}
.wrap{max-width:900px;margin:0 auto;padding:48px 34px 90px}
h1{font-size:2rem;line-height:1.35;text-align:center;margin:.4em 0 .3em}
.meta{text-align:center;color:var(--muted);font-size:.95rem;margin-bottom:2.2rem}
.abstract{background:var(--panel);border-left:3px solid var(--accent);padding:18px 26px;margin:2rem 0}
.abstract h3{margin:0 0 .6rem;font-size:1.05rem;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.toc{background:#fbfcfa;border:1px solid var(--line);border-radius:6px;padding:16px 26px;margin:2rem 0}
.toc h3{margin:0 0 .5rem;font-size:1rem;color:var(--muted)}
.toc ul{list-style:none;margin:0;padding:0;columns:2;column-gap:32px}
.toc li{break-inside:avoid;margin:.25rem 0;font-size:.92rem}
.toc li.subsection{padding-left:1rem;color:var(--muted);font-size:.86rem}
.toc a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--line)}
.toc a:hover{color:var(--accent)}
h2{font-size:1.45rem;margin-top:2.5rem;padding-bottom:.35rem;border-bottom:1px solid var(--line)}
h3{font-size:1.15rem;margin-top:1.9rem;color:#2e3a30}
h4{font-size:1.02rem;margin-top:1.4rem}
p{margin:.85rem 0;text-align:justify}
ul,ol{padding-left:1.6rem}
li{margin:.4rem 0}
.math{overflow-x:auto;margin:1.3rem 0;font-size:1.02rem;text-align:center}
table{border-collapse:collapse;width:100%;margin:1rem 0 1.6rem;font-size:.9rem;line-height:1.55}
th,td{border:1px solid var(--line);padding:9px 11px;text-align:left;vertical-align:top}
th{background:var(--panel)}
.caption{text-align:center;color:var(--muted);font-size:.88rem;margin:1.2rem 0 .4rem}
code{font: .88em ui-monospace,SFMono-Regular,Menlo,monospace;background:#f1f3f0;padding:1px 5px;border-radius:3px}
.refs{font-size:.94rem;color:#333}
.refs li{margin:.55rem 0}
.note{background:#fffaf0;border:1px solid #eadfc2;border-radius:6px;padding:11px 16px;font-size:.9rem;color:#6b5a34;margin-bottom:2rem}
@media print{.toc{display:none}.wrap{max-width:none;padding:0}}
"""

doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolveX · 2026 MCM Problem C 论文</title>
<style>{CSS}</style>
<script>window.MathJax={{tex:{{inlineMath:[['\\\\(','\\\\)']],displayMath:[['\\\\[','\\\\]']]}}}};</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head><body><div class="wrap">
<p class="note">由 SolveX 2.0 生成的 LaTeX 论文自动排版预览；数学公式由 MathJax 渲染（需联网）。原始 <code>main.tex</code> 可单独下载。</p>
<h1>{title}</h1>
<p class="meta">{author} &nbsp;·&nbsp; {date}</p>
<nav class="toc"><h3>Contents</h3><ul>{toc_html}</ul></nav>
{''.join(out)}
</div></body></html>"""

open(OUT, "w", encoding="utf-8").write(doc)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
print("sections in toc:", len(toc), "| blocks:", len(out))
