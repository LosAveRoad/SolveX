"""Model 1 entry script: deterministic end-to-end rerun of every output."""
import numpy as np
import model1_run
import model1_figs

if __name__ == "__main__":
    res, met = model1_run.main()
    figstats = model1_figs.main()
    # merge figure stats into results.json
    import json
    with open(model1_run.HERE / "results.json") as f:
        summary = json.load(f)
    summary["figure_stats"] = figstats
    with open(model1_run.HERE / "results.json", "w") as f:
        json.dump(summary, f, indent=1, default=float)
    print("run.py complete")
