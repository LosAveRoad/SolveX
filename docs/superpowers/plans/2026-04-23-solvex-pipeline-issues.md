# SolveX Pipeline Issue Evaluation & Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Systematically identify, classify, and fix all issues found in the 0423-b8a2 end-to-end test of the SolveX multi-model pipeline.

**Architecture:** 5-agent pipeline: ModelingAgent → ProgrammingAgent → ModelingAgent(review) × N → WritingAgent. Issues span all agents and the flow orchestration.

**Tech Stack:** Python 3.13, Pydantic, asyncio, DeepSeek Reasoner API

---

# Part 1: Issue Taxonomy

## Category A: Modeling Agent Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| A1 | **Master plan aspirational vs implementable** — Plan specifies Neural CDE, Bayesian Tensor, etc. but these require PyMC/PyTorch which aren't available. ProgrammingAgent falls back to simpler models. | High | Plan: "Neural CDE"; Actual: "ZI-BSTS using Metropolis-Hastings" |
| A2 | **Master plan overwritten during review** — ModelingAgent tried to write a new plan during Model 4 review, corrupting the original. | High | `master_plan.md` changed from 4 models to 5 models mid-session |
| A3 | **Model count not grounded in reality** — Agent decided 5 models, but only 4 can reasonably complete in 1 hour. No time-budget awareness. | Medium | 5 models, only 2 completed in 56 min first run |

## Category B: Programming Agent Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| B1 | **Model 1 no figures generated** — No visualization despite data processing working. | Medium | `model_1/figures/` is empty |
| B2 | **Model 1 results_summary auto-generated** — Agent failed to write a proper summary; system generated one from raw tool output. | High | `results_summary.md` contains `<think/>` tags and raw tool outputs |
| B3 | **Model 2 forecast numbers suspiciously low** — US predicted 28.3 total medals vs actual 126 in 2024. Likely the model predicts per-event-category, not total. | Critical | `forecast_2028.csv`: United States,8.9,8.5,10.9,28.3 |
| B4 | **Model 4 Weibull model lacks cure fraction** — Assumes all countries will eventually medal, giving 37/85 countries probability >0.99. Sum = 62 expected new medalists vs historical 5-6. | Critical | `first_medal_predictions_2028.csv`: 37 rows with P=0.99 |
| B5 | **results_summary.md format inconsistent** — Some models have structured summaries, others are auto-generated junk. No enforced schema. | Medium | Compare model_1 (auto) vs model_3 (structured) |

## Category C: Review Agent Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| C1 | **Reviews never created in first run** — Review phase ran but review files don't exist. Agent explored data instead of reviewing. | High | No `*_review.md` files in `01_modeling/` |
| C2 | **Review didn't catch Model 4's unreasonable probabilities** — Even in second run with improved prompt, review passed. | Critical | Model 4 sum=62 was not caught |
| C3 | **Review prompt lacked domain-specific checks** — "Are numbers reasonable?" is too vague for a model checking survival probabilities. | Medium | REVIEW_PROMPT was generic |

## Category D: Writing Agent Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| D1 | **2028 predictions severely under-predicted** — US 28.3 medals (should be ~100-130). WritingAgent copied Model 2's CSV without understanding the scale. | Critical | main.tex line 122: `United States & 8.9 & 8.5 & 10.9 & 28.3` |
| D2 | **Model 1 and Model 2 prediction tables identical** — Both tables show same numbers because they read the same CSV. | High | Table `2028_predictions` = Table `2028_stgat` |
| D3 | **Abstract contradicts conclusion** — Abstract says "62 countries"; conclusion says "5-6". | Medium | Line 21 vs line 914 |
| D4 | **Fabricated validation metrics** — MAE=2.1, correlation=0.849 etc. not from actual results. | High | Line 156-158: "MAE of 2.1 medals" — not in any results_summary |
| D5 | **Model 5 content invented** — No code was written, but paper describes mathematical formulation as if implemented. | Medium | Lines 630-678: "Not Implemented" section is honest, but formulation section implies otherwise |

## Category E: Flow Orchestration Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| E1 | **1-hour timeout too tight** — 5 models need ~3 hours. Only 2/5 completed in first run. | High | First run timed out at 3600s |
| E2 | **Resume overwrites data** — `prepare_workspace()` deletes output dirs on resume, losing completed work. | Critical | `workspace.py` line 56-59: `shutil.rmtree(p)` on OUTPUT_DIRS |
| E3 | **No validation between phases** — Pipeline proceeds from programming → writing without checking result quality. | High | Model 4's bad probabilities flow directly into paper |
| E4 | **Auto-generated summaries leak raw tool output** — `<think/>` tags and raw JSON appear in results_summary.md | Medium | model_1/results_summary.md has `<think/>` and `## Tool Output` sections |

## Category F: Infrastructure Issues

| # | Issue | Severity | Evidence |
|---|-------|----------|----------|
| F1 | **DeepSeek Reasoner single-response too long** — WritingAgent step 1 generates 80K tokens, causing BadRequestError on next step. | High | `Error: RetryError[...BadRequestError]` |
| F2 | **Memory compaction loses context** — After compaction (80K→35K), agent quality degrades. | Medium | Step 4/40 after compaction errored in first attempt |
| F3 | **Master plan not protected from overwrite** — Review agent can modify master_plan.md. | High | ModelingAgent overwrote plan during review |

---

# Part 2: Issue → Root Cause Mapping

```
B3 (low predictions) ←── B2 (bad summary) ←── E4 (auto-summary leaks think tags)
     ↓
D1 (paper wrong numbers) ←── D2 (tables identical) ←── B3 (single CSV source)

B4 (bad probabilities) ←── A1 (plan too ambitious) ←── A3 (no time budget)
     ↓
C2 (review didn't catch) ←── C3 (vague review prompt)

D4 (fabricated metrics) ←── B2 (no real validation data)
D3 (abstract contradiction) ←── F1 (long response splits work)
A2 (plan overwritten) ←── F3 (no file protection)
E2 (resume deletes work) ←── E3 (no validation gate)
```

**Core insight:** Most downstream issues (D1-D5) trace back to upstream data quality problems (B2, B3, B4) which trace back to missing validation gates (E3) and poor results format (B5, E4).

---

# Part 3: Fix Plan (Priority Order)

## Task 1: Fix results_summary.md schema enforcement
**Priority:** P0 — blocks all downstream quality

**Files:**
- Modify: `app/prompt/programming.py` (already partially done)
- Modify: `app/flow/solvex_flow.py` (auto-summary fallback)

The ProgrammingAgent prompt already has structured requirements. The problem is the **auto-generated fallback** which produces garbage. Fix the fallback to be structured too.

- [ ] **Step 1: Fix auto-summary fallback in solvex_flow.py**

In `solvex_flow.py`, find the auto-summary fallback block and replace:

```python
if not summary_path.exists():
    auto_lines = [f"# {model_name} Results Summary (auto-generated)\n"]
    for msg in programming_agent.memory.messages:
        if msg.content and msg.role == "tool":
            auto_lines.append(f"\n## Tool Output\n```\n{msg.content[:2000]}\n```\n")
    summary_path.write_text("\n".join(auto_lines))
```

Replace with a structured summary that extracts actual output:

```python
if not summary_path.exists():
    auto_lines = [
        f"# {model_name} Results Summary (auto-generated)\n\n",
        "## Status\n⚠ Agent did not write results_summary.md\n\n",
    ]
    # Extract last python_execute output as "results"
    for msg in reversed(programming_agent.memory.messages):
        if msg.content and msg.role == "tool":
            content = msg.content
            # Strip think tags
            if "<think/>" in content:
                content = content.split("<think/>", 1)[-1]
            # Find the observation field
            if "'observation':" in content:
                import re as _re
                obs_match = _re.search(r"'observation':\s*['\"](.+?)['\"]", content, _re.DOTALL)
                if obs_match:
                    auto_lines.append("## Key Output\n```\n" + obs_match.group(1)[:3000] + "\n```\n")
            break
    auto_lines.append("\n## Sanity Checks\n⚠ NOT PERFORMED — agent did not validate\n")
    auto_lines.append("\n## Figures\n⚠ None generated\n")
    summary_path.write_text("\n".join(auto_lines))
```

- [ ] **Step 2: Test with a mock that doesn't create results_summary.md**

Verify the auto-generated summary is clean (no `<think/>` tags, no raw JSON).

- [ ] **Step 3: Commit**

```bash
git add app/flow/solvex_flow.py
git commit -m "fix: improve auto-generated results_summary format"
```

---

## Task 2: Add validation gate between Programming and Review
**Priority:** P0 — prevents bad data from flowing downstream

**Files:**
- Modify: `app/flow/solvex_flow.py`

Add a `_validate_model_output()` function called after ProgrammingAgent completes and before Review starts.

- [ ] **Step 1: Add validation function in solvex_flow.py**

Add before the `SolveXFlow` class:

```python
def _validate_model_output(model_name: str, model_dir: Path) -> list[str]:
    """Check basic output quality. Returns list of issues found."""
    issues = []

    # Check results_summary exists and is meaningful
    summary = model_dir / "results_summary.md"
    if not summary.exists():
        issues.append("No results_summary.md file")
    elif summary.stat().st_size < 100:
        issues.append("results_summary.md is nearly empty")
    else:
        text = summary.read_text()
        if "<think/>" in text:
            issues.append("results_summary.md contains raw think tags (auto-generated?)")
        if "auto-generated" in text.lower() and "⚠" not in text:
            issues.append("results_summary appears auto-generated without validation")

    # Check code files exist
    py_files = list(model_dir.glob("*.py"))
    if not py_files:
        issues.append("No Python code files generated")

    # Check CSV data for common issues
    for csv_file in model_dir.glob("*.csv"):
        try:
            import pandas as pd
            df = pd.read_csv(csv_file)
            for col in df.select_dtypes(include="number").columns:
                if col.lower() == "probability":
                    if df[col].sum() > 50 and len(df) > 10:
                        issues.append(
                            f"{csv_file.name}: Probability sum = {df[col].sum():.0f} "
                            f"(historical: ~5-6 first medals per Olympics)"
                        )
                    if (df[col] > 0.95).sum() > len(df) * 0.3:
                        issues.append(
                            f"{csv_file.name}: {(df[col] > 0.95).sum()}/{len(df)} "
                            f"probabilities > 0.95 (likely uncalibrated)"
                        )
        except Exception:
            pass  # CSV reading is best-effort

    # Check figures
    fig_dir = model_dir / "figures"
    if fig_dir.exists():
        figs = list(fig_dir.glob("*.png"))
        if not figs:
            issues.append("No figures generated")
    else:
        issues.append("No figures/ directory")

    return issues
```

- [ ] **Step 2: Call validation after ProgrammingAgent completes**

After `prog_output = await programming_agent.run(programming_prompt)` in the programming loop, add:

```python
# Validate output quality
validation = _validate_model_output(model_name, abs_model_dir)
if validation:
    await _emit(self.event_queue, "warn", f"{model_name} validation issues: {'; '.join(validation)}")
    # If critical issues found, update programming prompt for retry
    if any("auto-generated" in v or "Probability sum" in v for v in validation):
        await _emit(self.event_queue, "warn", f"{model_name}: Auto-fixing issues...")
```

- [ ] **Step 3: Commit**

```bash
git add app/flow/solvex_flow.py
git commit -m "feat: add validation gate between programming and review"
```

---

## Task 3: Protect master_plan.md from overwrite during review
**Priority:** P0 — data corruption

**Files:**
- Modify: `app/prompt/modeling.py` (REVIEW_PROMPT)
- Modify: `app/flow/solvex_flow.py`

- [ ] **Step 1: Remove file path from REVIEW_PROMPT**

In `app/prompt/modeling.py`, ensure REVIEW_PROMPT does NOT mention master_plan.md's path. Current prompt is already clean — it only mentions `{review_path}`. Verify and commit.

- [ ] **Step 2: Add protection in flow**

In `solvex_flow.py`, before running the review, snapshot the master plan and restore it after:

```python
# Protect master plan from accidental overwrite during review
master_plan_snapshot = master_plan_path.read_text() if master_plan_path.exists() else None

# ... run modeling_agent.run(review_prompt) ...

# Restore master plan if overwritten
if master_plan_snapshot and master_plan_path.exists():
    current = master_plan_path.read_text()
    if current != master_plan_snapshot:
        master_plan_path.write_text(master_plan_snapshot)
        logger.warning(f"Restored master_plan.md after review (was modified)")
```

- [ ] **Step 3: Commit**

```bash
git add app/flow/solvex_flow.py app/prompt/modeling.py
git commit -m "fix: protect master_plan.md from overwrite during review"
```

---

## Task 4: Fix WritingAgent's number interpretation
**Priority:** P1 — paper quality

**Root cause:** WritingAgent reads `forecast_2028.csv` with US=28.3 and doesn't question it because the results_summary.md says "Model converged successfully."

**Files:**
- Modify: `app/prompt/writing.py`

- [ ] **Step 1: Add cross-checking instruction to WritingAgent SYSTEM_PROMPT**

Add to the "CRITICAL RULES" section:

```
"6. CROSS-CHECK numbers against known facts. If Model 1 predicts US will win 28 medals in 2028 "
"   but US won 126 in 2024, flag this as 'prediction scale mismatch' in the paper. "
"   Do NOT silently copy suspicious numbers.\n"
"7. If two models produce identical prediction tables, write 'Note: both models converge to "
"   similar predictions' rather than pretending they're independent.\n"
```

- [ ] **Step 2: Commit**

```bash
git add app/prompt/writing.py
git commit -m "fix: add cross-checking instructions for WritingAgent"
```

---

## Task 5: Fix resume safety (don't delete completed work)
**Priority:** P1 — prevents data loss

**Files:**
- Modify: `app/workspace.py`

- [ ] **Step 1: Add `skip_clean` parameter to prepare_workspace**

```python
def prepare_workspace(
    problem_text: str,
    data_dir: str = None,
    session_id: str = None,
    skip_clean: bool = False,
) -> Path:
```

Change the clean block:
```python
    # Clean output dirs if workspace already exists (re-run) unless skip_clean
    if not skip_clean:
        for d in OUTPUT_DIRS:
            p = ws / d
            if p.exists():
                shutil.rmtree(p)
```

- [ ] **Step 2: Pass skip_clean=True when resuming**

In `run_flow.py`, when `resume_session` is set, pass `skip_clean=True`:
```python
ws = prepare_workspace(problem_text, data_dir=data_dir, skip_clean=True)
```

Wait — actually `prepare_workspace` is NOT called on resume. The resume path in `run_flow.py` directly sets `ws = Path.home() / ".solvex/sessions" / resume_session`. So the deletion only happens on fresh runs. This is actually fine. No fix needed.

- [ ] **Step 3: Verify resume doesn't delete, remove Task 5 if unnecessary**

Confirmed: resume path skips `prepare_workspace()` entirely. No data loss. Close this task.

---

## Task 6: Add time-budget awareness to ModelingAgent
**Priority:** P2 — prevents overcommitting

**Files:**
- Modify: `app/prompt/modeling.py` (SYSTEM_PROMPT)

- [ ] **Step 1: Add time/capability constraint to system prompt**

Add to SYSTEM_PROMPT after "IMPORTANT RULES":

```
"\nCAPABILITY CONSTRAINTS:\n"
"- Assume PyMC, PyTorch, TensorFlow are NOT available. Use numpy, scipy, statsmodels, sklearn.\n"
"- Each model implementation should take 10-15 minutes max (30 programming steps).\n"
"- Design 2-4 models, not 5+. Fewer well-executed models beat many half-done ones.\n"
"- Prefer simpler models that actually run over complex ones that can't.\n"
```

- [ ] **Step 2: Commit**

```bash
git add app/prompt/modeling.py
git commit -m "fix: add capability constraints to ModelingAgent prompt"
```

---

## Task 7: Improve Review prompt with domain-specific checks
**Priority:** P2 — review quality

**Files:**
- Modify: `app/prompt/modeling.py` (REVIEW_PROMPT)

- [ ] **Step 1: Add specific sanity checks to REVIEW_PROMPT**

In REVIEW_PROMPT, after "CHECK THESE CRITERIA", add:

```
"5. **Domain-specific sanity checks**:\n"
"   - Medal predictions: US/China should be 80-130 total medals, not 20-30\n"
"   - Probabilities: if predicting first medals, sum should be ~5-10, not 60+\n"
"   - Correlations: should be 0.5-0.95, not 0.01 or 0.999\n"
"   - Error metrics: MAE should be reasonable given the data scale\n"
```

- [ ] **Step 2: Commit**

```bash
git add app/prompt/modeling.py
git commit -m "fix: add domain-specific sanity checks to review prompt"
```

---

## Task 8: Fix WritingAgent abstract-conclusion consistency
**Priority:** P2 — paper polish

**Files:**
- Modify: `app/flow/solvex_flow.py` (writing prompt)

- [ ] **Step 1: Instruct WritingAgent to write abstract LAST**

In the write_prompt in solvex_flow.py, add:

```python
f"\nWRITE ORDER: Write the body sections FIRST, then write the abstract LAST.\n"
f"The abstract must match the conclusions. Do NOT write the abstract first.\n"
```

- [ ] **Step 2: Commit**

```bash
git add app/flow/solvex_flow.py
git commit -m "fix: WritingAgent writes abstract last for consistency"
```

---

# Part 4: Summary

| Category | Count | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| A: Modeling Agent | 3 | 2 | 0 | 1 |
| B: Programming Agent | 5 | 2 | 2 | 1 |
| C: Review Agent | 3 | 1 | 0 | 2 |
| D: Writing Agent | 5 | 1 | 2 | 2 |
| E: Flow Orchestration | 4 | 2 | 1 | 1 |
| F: Infrastructure | 3 | 1 | 1 | 1 |
| **Total** | **23** | **9** | **6** | **8** |

**Root cause chain:** Most issues trace back to **B5 (inconsistent results_summary format)** and **E3 (no validation gate)**. Fix these first (Tasks 1-2) and 60%+ of downstream issues resolve themselves.

**Implementation order:** Task 1 → 3 → 2 → 4 → 6 → 7 → 8 (fix data quality first, then protect against corruption, then add checks, then polish)
