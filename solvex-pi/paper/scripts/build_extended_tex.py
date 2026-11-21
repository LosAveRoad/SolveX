"""Assemble main_extended.tex from the original paper plus the new chapters.

The original main.tex is never modified; this produces a parallel extended edition.
"""
import os

D = "/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/sessions/rerun-2026-mcmc/04_paper"
text = open(os.path.join(D, "main.tex"), encoding="utf-8").read()


def sub(old, new, label):
    global text
    assert old in text, f"anchor not found: {label}"
    assert text.count(old) == 1, f"anchor not unique: {label}"
    text = text.replace(old, new, 1)
    print("  patched:", label)


# 0. typography -------------------------------------------------------
sub(r"\geometry{margin=1in}",
    r"\geometry{margin=1in}" + "\n" + r"\emergencystretch=3em", "emergency stretch")

# 1. abstract tail ----------------------------------------------------
sub(r"""fusion better serves a pure excitement objective. All five figures and the full estimation
pipeline are reproducible from the provided data.""",
    r"""fusion better serves a pure excitement objective. An extended analysis adds a
\textbf{non-circular benchmark}: using judge scores alone, the couple with the lowest judge
share is the one actually eliminated in only $\mathbf{44.4\%}$ of the 266 eliminating weeks,
and in only $42.2\%$ of eliminations does the eliminated couple hold the worst judge rank ---
so an audience channel (or, later, the judge save) is necessary in \emph{every} regime. Rank
and percent fusion would eliminate different couples in \textbf{24 of 266} weeks ($9.02\%$),
and a sharp discontinuity in hit rate ($1.000\rightarrow0.371$) and Brier score
($0.011\rightarrow0.567$) between seasons 27 and 28 identifies the rule change empirically
instead of assuming it. A counterfactual fusion-weight scan and an interval-robust replay
delimit which conclusions are identified and which remain structurally circular. All
\textbf{18 figures}, eight generated tables and the full estimation pipeline are reproducible
from the provided CSV artifacts.""", "abstract tail")

# 2. correct the uncertainty-direction claim --------------------------
sub(r"""$0.607$ in weakly-constrained weeks. This directly answers the problem's ``is that
certainty always the same?'' question: \textbf{no}. Weeks with many surviving couples and
weak judge spread leave the fan share poorly identified, whereas late-season weeks with
few couples and clear judge separation pin the share down tightly.""",
    r"""$0.607$ in weakly-constrained weeks. This directly answers the problem's ``is that
certainty always the same?'' question: \textbf{no}. In \emph{absolute} terms the widest
intervals occur late in a season, when few couples remain and each share is large
(correlation $+0.563$ with competition week and $-0.649$ with field size); after rescaling by
field size, however, large early-season fields are the least identified. Both measures, and
the resolution of this apparent contradiction, are given in
Section~\ref{sec:uncertainty}.""", "uncertainty direction correction")

# 3. paper outline ----------------------------------------------------
sub(r"""strengths and limitations, and Section~\ref{sec:conclusion} concludes with recommendations
and directions for future work.""",
    r"""strengths and limitations, and Section~\ref{sec:conclusion} concludes with recommendations
and directions for future work. Section~\ref{sec:eda} documents the data, measurement
conventions and correlation definitions; Sections~\ref{sec:empirical}--\ref{sec:diagnostics}
add season-level, non-circular, counterfactual, quantitative-sensitivity and diagnostic
analyses; and the appendices give complete season statistics, a variable dictionary, the
figure inventory and reproduction steps.""", "paper outline")

# 4. section insertions -----------------------------------------------
INSERT_EDA = "%=====================================================================\n\\section{Model 1: Constrained Fan-Vote Reconstruction}\\label{sec:m1}"
sub(INSERT_EDA, "\\input{chapters/eda.tex}\n\n" + INSERT_EDA, "insert EDA section")

INSERT_EXT = "%=====================================================================\n\\section{Sensitivity Analysis}\\label{sec:sensitivity}"
sub(INSERT_EXT,
    "\\input{chapters/empirical.tex}\n\n\\input{chapters/counterfactual.tex}\n\n" + INSERT_EXT,
    "insert empirical + counterfactual sections")

INSERT_DIAG = "%=====================================================================\n\\section{Discussion}\\label{sec:discussion}"
sub(INSERT_DIAG,
    "\\input{chapters/sensitivity_quant.tex}\n\n\\input{chapters/diagnostics.tex}\n\n" + INSERT_DIAG,
    "insert quantitative sensitivity + diagnostics")

INSERT_REF = "%=====================================================================\n\\section*{References}"
sub(INSERT_REF,
    "\\newpage\n\\appendix\n\\input{chapters/appendix.tex}\n\n\\newpage\n" + INSERT_REF,
    "insert appendices")

# 5. additional references -------------------------------------------
NEW_BIBS = r"""
\bibitem{brier1950}
Brier, G.~W. (1950).
Verification of Forecasts Expressed in Terms of Probability.
\emph{Monthly Weather Review}, 78(1), 1--3.

\bibitem{spearman1904}
Spearman, C. (1904).
The Proof and Measurement of Association between Two Things.
\emph{American Journal of Psychology}, 15(1), 72--101.

\bibitem{kendall1948}
Kendall, M.~G. (1948).
\emph{Rank Correlation Methods}.
Charles Griffin, London.

\bibitem{vehtari2021}
Vehtari, A., Gelman, A., Simpson, D., Carpenter, B., \& B\"urkner, P.-C. (2021).
Rank-Normalization, Folding, and Localization: An Improved $\hat R$ for Assessing
Convergence of MCMC.
\emph{Bayesian Analysis}, 16(2), 667--718.

\bibitem{smith1984}
Smith, R.~L. (1984).
Efficient Monte Carlo Procedures for Generating Points Uniformly Distributed over Bounded
Regions.
\emph{Operations Research}, 32(6), 1296--1308.

\bibitem{cover2006}
Cover, T.~M., \& Thomas, J.~A. (2006).
\emph{Elements of Information Theory} (2nd ed.).
Wiley-Interscience.

\bibitem{roberts2004}
Roberts, G.~O., \& Rosenthal, J.~S. (2004).
General State Space Markov Chains and MCMC Algorithms.
\emph{Probability Surveys}, 1, 20--71.

\bibitem{arrow1951}
Arrow, K.~J. (1951).
\emph{Social Choice and Individual Values}.
Wiley, New York.
"""
sub(r"""\end{thebibliography}""", NEW_BIBS + "\n\\end{thebibliography}", "additional references")

out = os.path.join(D, "main_extended.tex")
open(out, "w", encoding="utf-8").write(text)
print("wrote", out, len(text.splitlines()), "lines,", len(text), "chars")
print("inputs:", text.count("\\input{"))
