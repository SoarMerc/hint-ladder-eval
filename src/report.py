"""Builds the chart and FINDINGS.md.

Meant to be understood in a minute by someone who won't read the code: one
number, one chart, one table.

A few chart notes, since they're deliberate. One panel per language instead of
one crowded plot, because 60 lines on a single axis is a hairball. Individual
skills are grey and recessive; only the mean gets colour. Three colours, fixed
order, taken from a palette checked for colour-blind separation. Language is in
each panel title so colour isn't carrying the meaning on its own.
"""

from __future__ import annotations

from pathlib import Path

from .config import LANGUAGE_NAMES, ROOT, Config
from .detect import cross_language_gaps, summarise
from .schemas import Curve, Detection, RunReport
from .tag import drift_rate

# First three slots of the validated categorical palette, in fixed order.
# These three are the documented subset that clears the all-pairs colour-vision
# gates in both modes, which is the case small multiples fall under.
LIGHT = {
    "series": ["#2a78d6", "#eb6834", "#1baf7a"],
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "faint": "#c3c2b7",
}
DARK = {
    "series": ["#3987e5", "#d95926", "#199e70"],
    "surface": "#1a1a19",
    "ink": "#ffffff",
    "secondary": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "faint": "#52514e",
}


def _mean_curve(curves: list[Curve]) -> list[float]:
    if not curves:
        return []
    n = len(curves[0].accuracy)
    return [sum(c.accuracy[k] for c in curves) / len(curves) for k in range(n)]


def draw_chart(
    curves: list[Curve],
    detections: list[Detection],
    cfg: Config,
    path: Path,
    theme: dict[str, object],
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    languages = [
        lang for lang in cfg.languages if any(c.language == lang for c in curves)
    ]
    flagged_by_lang: dict[str, int] = {}
    for d in detections:
        if d.status == "leaked":
            flagged_by_lang[d.language] = flagged_by_lang.get(d.language, 0) + 1

    fig, axes = plt.subplots(
        1, len(languages), figsize=(4.2 * len(languages), 4.0), sharey=True
    )
    if len(languages) == 1:
        axes = [axes]
    fig.patch.set_facecolor(theme["surface"])

    xs = list(range(cfg.max_hint_level + 1))

    for idx, (ax, lang) in enumerate(zip(axes, languages)):
        colour = theme["series"][idx % len(theme["series"])]
        subset = [c for c in curves if c.language == lang]

        for c in subset:
            ax.plot(
                xs,
                c.accuracy,
                color=theme["faint"],
                linewidth=0.8,
                alpha=0.45,
                zorder=1,
                label="individual skills" if c is subset[0] else None,
            )

        mean = _mean_curve(subset)
        ax.plot(
            xs,
            mean,
            color=colour,
            linewidth=2.0,
            marker="o",
            markersize=6,
            markeredgecolor=theme["surface"],
            markeredgewidth=1.5,
            zorder=3,
            label="mean across skills",
        )

        # Selective direct labels: the two ends of the mean, not every point.
        # The right-hand label sits below its point so it cannot collide with
        # the panel title when the mean reaches the top of the axis.
        for k, dx, dy, ha in (
            (0, 6, 7, "left"),
            (cfg.max_hint_level, -6, -16, "right"),
        ):
            ax.annotate(
                f"{mean[k]:.0%}",
                xy=(k, mean[k]),
                xytext=(dx, dy),
                textcoords="offset points",
                ha=ha,
                fontsize=9,
                color=theme["secondary"],
                zorder=4,
            )

        leaked = flagged_by_lang.get(lang, 0)
        ax.set_title(
            f"{LANGUAGE_NAMES.get(lang, lang)}\n{leaked} of {len(subset)} ladders leaked early",
            fontsize=11,
            color=theme["ink"],
            pad=10,
        )
        ax.set_facecolor(theme["surface"])
        ax.set_xlabel("hints shown", fontsize=9, color=theme["muted"])
        ax.set_xticks(xs)
        ax.set_ylim(-0.03, 1.06)  # headroom so a mean at 100% is not clipped
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.grid(axis="y", color=theme["grid"], linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(theme["axis"])
            ax.spines[side].set_linewidth(1.0)
        ax.tick_params(colors=theme["muted"], labelsize=9)

        if idx == 0:
            ax.set_ylabel("student accuracy", fontsize=9, color=theme["muted"])
            ax.set_yticklabels([f"{v:.0%}" for v in [0, 0.25, 0.5, 0.75, 1.0]])
            legend = ax.legend(
                loc="upper left",
                frameon=False,
                fontsize=8.5,
                labelcolor=theme["secondary"],
            )
            for text in legend.get_texts():
                text.set_color(theme["secondary"])

    fig.suptitle(
        "Where the hint ladder gives the answer away",
        fontsize=13,
        color=theme["ink"],
        y=1.02,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=theme["surface"], bbox_inches="tight")
    plt.close(fig)
    return path


def write_findings(report: RunReport, cfg: Config, chart: Path) -> Path:
    counts = summarise(report.detections)
    total = len(report.detections)
    leaked = counts.get("leaked", 0)
    gaps = cross_language_gaps(report.detections)

    lines: list[str] = []
    add = lines.append

    add("# Findings")
    add("")
    if report.mock:
        add(
            "> **These numbers are simulated, not measured.** This run used "
            "`--mock`, which replaces every model call with a deterministic "
            "simulator that plants leaks at known levels. It exists so the "
            "pipeline can be run and reviewed without an API key, and so the "
            "detector can be tested against ladders whose true leak level is "
            "known. Re-run without `--mock` for real measurements."
        )
        add("")

    add("## What this measures")
    add("")
    add(
        "A tutor that teaches through hints is supposed to make the student do "
        "the thinking. Each hint helps a bit more than the last, and none of "
        "them gives the answer away. This checks whether that holds."
    )
    add("")
    add(
        "It writes a question, an answer, and a ladder of "
        f"{cfg.max_hint_level} hints. Then it shows a model **only the hints, "
        "never the question**, and asks what the answer to the hidden question "
        "must be."
    )
    add("")
    add(
        "- If the ladder is doing its job, the model can't answer. Without the "
        "question there's nothing to solve, because the hints describe a method "
        "rather than handing over a result."
    )
    add(
        "- If the ladder leaks, at some hint the model can answer **from the "
        "hints alone**, and every hint after that was decoration."
    )
    add("")
    add(
        "Hiding the question is what makes this work. The obvious approach - "
        "show the student the question and watch its score climb as hints "
        "arrive - doesn't work any more, because a small current model answers "
        "grade 6-8 questions with no hints at all. Its score starts at the top "
        "and never moves. Hiding the question puts the floor back at zero no "
        "matter how good the model is."
    )
    add("")
    add(
        "This also catches what a plain text search would miss. On one "
        "generated item, none of the hints contained the answer anywhere in "
        "their text, and the model still worked it out from the first three."
    )
    add("")
    add(
        "The failure is worth catching because it's silent. Nothing errors. The "
        "student gets it right, the mastery score goes up, and no learning "
        "happened."
    )
    add("")

    add("## Headline")
    add("")
    add(f"**{leaked} of {total} ladders gave the answer away earlier than intended.**")
    add("")
    n_skills = len({d.skill_code for d in report.detections})
    n_langs = len({d.language for d in report.detections})
    if n_langs > 1:
        add(
            f"Those {total} ladders are {n_skills} standards measured in "
            f"{n_langs} languages, not {total} independent items. The languages "
            "share a question and an answer by design, so they are correlated: "
            f"treat the underlying sample size as {n_skills}."
        )
        add("")
    add(f"![Leakage curves]({chart.name})")
    add("")

    add("## Results by outcome")
    add("")
    add("| outcome | count | what it means |")
    add("|---|---:|---|")
    add(
        f"| leaked | {counts.get('leaked', 0)} | the score jumped before the "
        "last hint, so the ladder gave the answer away early |"
    )
    add(
        f"| ok | {counts.get('ok', 0)} | the score climbed gradually, or only "
        "jumped at the last hint |"
    )
    add(
        f"| trivial | {counts.get('trivial', 0)} | answered with no hints at "
        "all, so the question itself is the problem |"
    )
    add(
        f"| no signal | {counts.get('no_signal', 0)} | the ladder barely moved "
        "accuracy, so leakage is not measurable on this item |"
    )
    add("")

    if gaps:
        add("## Same ladder, different language")
        add("")
        add(
            "Same question, same answer, hints translated. These are the "
            "ladders that hold up in English and lose it in another language."
        )
        add("")
        add("| skill | language | leaks at hint | English leaks at hint | earlier by |")
        add("|---|---|---:|---:|---:|")
        for row in gaps:
            add(
                f"| {row['skill_code']} | {LANGUAGE_NAMES.get(str(row['language']), row['language'])} "
                f"| {row['leak_level']} | {row['en_leak_level']} | {row['levels_earlier']} |"
            )
        add("")

    flagged = [d for d in report.detections if d.flagged]
    if flagged:
        add("## Flagged items")
        add("")
        add("| skill | language | outcome | no hints | full ladder | note |")
        add("|---|---|---|---:|---:|---|")
        for d in sorted(flagged, key=lambda x: (x.status, x.skill_code)):
            add(
                f"| {d.skill_code} | {d.language} | {d.status} | {d.baseline:.0%} "
                f"| {d.ceiling:.0%} | {d.note} |"
            )
        add("")

    if report.tag_checks:
        rate = drift_rate(report.tag_checks)
        add("## Standards drift")
        add("")
        add(
            "Each question was shown to a second model that wasn't told which "
            "standard it was written for, and had to pick one from the list."
        )
        add("")
        add(
            f"**{rate:.0%} of items were tagged to a different standard than the "
            f"one they were filed under** ({len(report.tag_checks)} items checked)."
        )
        add("")

    if report.costs:
        add("## What this run cost")
        add("")
        add("| model | calls | input tokens | output tokens | USD |")
        add("|---|---:|---:|---:|---:|")
        for c in report.costs:
            usd = f"${c.usd:,.4f}" if c.priced else "not priced"
            add(
                f"| {c.model} | {c.calls:,} | {c.input_tokens:,} | "
                f"{c.output_tokens:,} | {usd} |"
            )
        add(f"| **total** | | | | **${report.total_usd:,.4f}** |")
        add("")
        if any(not c.priced for c in report.costs):
            add(
                "Models marked *not priced* have no verified rate in "
                "`config.py`, so their token counts are real but their dollar "
                "cost is not claimed and is excluded from the total. Add the "
                "rate there to price them."
            )
            add("")
        add(
            "Tracked per model because that's the number that decides whether "
            "this can run on every content change or only now and then."
        )
        add("")

    add("## What this doesn't prove")
    add("")
    add(
        "- **The content is synthetic.** Every question and hint was generated "
        "by this harness. Nothing was taken from any product."
    )
    add(
        f"- **Small sample.** {cfg.repeats} attempts per point on each curve. "
        "Enough to see a cliff, not enough to put an error bar on it."
    )
    add(
        "- **It's evidence, not proof.** A jump at hint *k* strongly suggests "
        "hint *k* carried the answer. Read the flagged ladders before acting."
    )
    add(
        "- **The student is a model, not a child.** It runs with reasoning "
        "turned off to sit closer to a struggling learner, but it's a stand-in."
    )
    add(
        "- **The judge never sees the hints**, but it's still a model marking "
        "free text, and it gets things wrong sometimes."
    )
    add(
        "- **No student data is involved anywhere.** There's no code path that "
        "reads a student record, and none is needed."
    )
    add("")

    # FINDINGS.md and the chart live at the repo root, not under the gitignored
    # results/ directory: they are the two things meant to be read and shared.
    path = ROOT / "FINDINGS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
