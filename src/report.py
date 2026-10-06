"""Builds the chart and FINDINGS.md.

Meant to be understood in a few minutes by someone who won't read the code:
one number, one chart, one real example, one table. Every term the page uses
is explained on the page.

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
from .generate import load_skills
from .schemas import Curve, Detection, Item, RunReport
from .tag import drift_rate

# Shown on the page in place of the detector's status names.
VERDICT = {
    "ok": "held",
    "no_signal": "no signal",
    "trivial": "no hints needed",
}

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
                label="one standard" if c is subset[0] else None,
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
            label="average",
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
        ax.set_xlabel("hints shown (question hidden)", fontsize=9, color=theme["muted"])
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
            ax.set_ylabel(
                "how often the AI student named the answer",
                fontsize=9,
                color=theme["muted"],
            )
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


def _verdict(d: Detection) -> str:
    if d.status == "leaked":
        return f"**leaks at hint {d.leak_level}**"
    return VERDICT.get(d.status, d.status)


def _chart_markdown(chart: Path) -> str:
    """Light chart, swapped for the dark one when the reader's GitHub is dark."""
    dark = chart.with_name(chart.stem + "_dark" + chart.suffix)
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{dark.name}">\n'
        f'  <img alt="Leakage curves" src="{chart.name}">\n'
        "</picture>"
    )


def _pick_example(report: RunReport) -> tuple[Item, Detection, Curve] | None:
    """The English ladder that gave its answer away earliest, if there is one."""
    leaked = sorted(
        (
            d
            for d in report.detections
            if d.status == "leaked" and d.language == "en" and d.leak_level
        ),
        key=lambda d: d.leak_level,
    )
    for d in leaked:
        item = next(
            (
                i
                for i in report.items
                if i.skill_code == d.skill_code and i.language == d.language
            ),
            None,
        )
        curve = next(
            (
                c
                for c in report.curves
                if c.skill_code == d.skill_code
                and c.language == d.language
                and c.condition == d.condition
            ),
            None,
        )
        if item and curve:
            return item, d, curve
    return None


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


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

    n_skills = len({d.skill_code for d in report.detections})
    languages = [
        lang for lang in cfg.languages if any(d.language == lang for d in report.detections)
    ]
    n = cfg.max_hint_level

    add(
        f"**In one line: {leaked} of {total} hint ladders gave the answer away "
        "before the last hint.**"
    )
    add("")
    if len(languages) > 1:
        add(
            f"Those {total} ladders are {n_skills} questions, each in "
            f"{len(languages)} languages. The translations share a question and "
            "answer, so they tend to pass or fail together: think of this as "
            f"{n_skills} findings, not {total}."
        )
        add("")

    add("## What was tested")
    add("")
    add(
        "A tutor that teaches through hints is meant to make the student do the "
        "thinking. Each hint helps a little more than the last, and none of "
        "them hands over the answer. This checks whether that holds."
    )
    add("")
    add(
        f"For each of {n_skills} school standards, an AI wrote one practice "
        f"question, its answer, and {n} hints. Then a second AI, playing the "
        "student, was shown **the hints but never the question**: first no "
        "hints, then hint 1, then hints 1 and 2, and so on. Each time it was "
        f"asked what the answer must be, and it had {cfg.repeats} tries at each "
        "step."
    )
    add("")
    add(
        "- If the hints are doing their job, it can't answer. It doesn't know "
        "what the question was, and the hints only describe how to work it out."
    )
    add(
        "- If it *can* answer, the hints gave the answer away on their own. "
        "Every hint after that point was decoration."
    )
    add("")
    add(
        "Why hide the question? Because today's AI models answer grade 6-8 "
        "questions correctly with no hints at all, so showing them the question "
        "tells you nothing about the hints. With the question hidden, the hints "
        "are the only thing it has to go on."
    )
    add("")

    add("### Words used on this page")
    add("")
    add(
        "- **Standard**: one skill from the Common Core, the public list of what "
        "US students are expected to learn in each grade. The codes read left "
        "to right: `6.EE.B.7` is grade 6, Expressions & Equations, group B, "
        "item 7. Codes starting `RL`, `RI` or `L` are English (reading stories, "
        "reading non-fiction, language). The table below says what each one "
        "covers."
    )
    add(
        f"- **Hint ladder**: the {n} hints for one question, in order from "
        f"vaguest to most helpful. Hint {n} is meant to be the most help a "
        "student gets without being told the answer."
    )
    add(
        "- **Leaks at hint 2**: from hint 2 onwards, the AI student could name "
        f"the answer without seeing the question. The ladder was meant to hold "
        f"until hint {n}."
    )
    add(
        "- **Held**: the answer never became findable early. Either the AI "
        "student couldn't name it at all, or only on the last hint."
    )
    add(
        "- **No signal**: the hints barely changed anything, so there's nothing "
        "to measure on this question."
    )
    add("")

    add(_chart_markdown(chart))
    add("")
    add(
        f"Each panel is one language. A grey line is one standard; the coloured "
        "line is the average. Left edge: no hints shown. Right edge: all "
        f"{n} hints. A line that sits at the bottom and then shoots to the top "
        "is a ladder that gave the answer away at that hint."
    )
    add("")

    example = _pick_example(report)
    if example and not report.mock:
        item, d, curve = example
        add("## A real example")
        add("")
        add(f"Standard `{item.skill_code}`, in English. The question was:")
        add("")
        add(f"> {item.question}")
        add("")
        add(f"The answer is **{item.answer}**. Here's what the AI student saw, "
            "without the question, and how often it named that answer:")
        add("")
        add("| hints shown | the newest hint | named the answer |")
        add("|---|---|---:|")
        add(
            f"| none | | {round(curve.accuracy[0] * cfg.repeats)} of {cfg.repeats} |"
        )
        for k, hint in enumerate(item.hints, start=1):
            mark = " ← answer findable from here" if k == d.leak_level else ""
            add(
                f"| {k} | {_cell(hint)}{mark} | "
                f"{round(curve.accuracy[k] * cfg.repeats)} of {cfg.repeats} |"
            )
        add("")
        add(
            f"Hint {d.leak_level} lays out enough of the working that the answer "
            "follows without ever seeing the question. A student who reads it "
            f"has nothing left to figure out, and hints {d.leak_level + 1} "
            f"{'and' if n - d.leak_level == 2 else 'to'} {n} never get used."
            if d.leak_level < n - 1
            else f"Hint {d.leak_level} lays out enough of the working that the "
            "answer follows without ever seeing the question."
        )
        add("")

    add("## Every standard, every language")
    add("")
    skills = {s.code: s for s in load_skills(cfg)}
    by_cell = {(d.skill_code, d.language): d for d in report.detections}
    codes = [code for code in skills if any(k[0] == code for k in by_cell)]
    names = [LANGUAGE_NAMES.get(lang, lang) for lang in languages]
    add("| standard | what the question tests | " + " | ".join(names) + " |")
    add("|---|---|" + "---|" * len(languages))
    for code in codes:
        cells = [
            _verdict(by_cell[(code, lang)]) if (code, lang) in by_cell else ""
            for lang in languages
        ]
        add(
            f"| `{code}` (grade {skills[code].grade}) | "
            f"{_cell(skills[code].description)} | " + " | ".join(cells) + " |"
        )
    add("")
    add(
        "| result | count |\n|---|---:|\n"
        + "\n".join(
            f"| {label} | {counts.get(status, 0)} |"
            for status, label in (
                ("leaked", "leaked early"),
                ("ok", "held"),
                ("no_signal", "no signal"),
                ("trivial", "no hints needed"),
            )
        )
    )
    add("")

    if len(languages) > 1:
        add("## Did translation make it worse?")
        add("")
        per_lang = ", ".join(
            f"{sum(d.status == 'leaked' and d.language == lang for d in report.detections)}"
            f" in {LANGUAGE_NAMES.get(lang, lang)}"
            for lang in languages
        )
        add(
            "Same question, same answer, only the hints translated. The "
            "expectation was that hints written carefully in English would "
            f"get leakier in translation. Leaks out of {n_skills}: {per_lang}."
        )
        add("")
        if gaps:
            add(
                "These ladders gave the answer away earlier in translation than "
                "in English:"
            )
            add("")
            add("| standard | language | leaks at hint | in English, leaks at hint |")
            add("|---|---|---:|---:|")
            for row in gaps:
                add(
                    f"| `{row['skill_code']}` | "
                    f"{LANGUAGE_NAMES.get(str(row['language']), row['language'])} "
                    f"| {row['leak_level']} | {row['en_leak_level']} |"
                )
            add("")
        else:
            add("No ladder gave the answer away earlier in translation.")
            add("")

    if report.tag_checks:
        rate = drift_rate(report.tag_checks)
        add("## Is each question testing the skill it's labelled with?")
        add("")
        add(
            "A separate check. Each English question was given to another AI "
            "that wasn't told which standard it was written for, and asked to "
            "pick the standard from the list. When it picks a different one, the "
            "question has drifted away from the skill it claims to teach."
        )
        add("")
        add(
            f"**It picked a different standard {rate:.0%} of the time** "
            f"({len(report.tag_checks)} questions checked)."
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
        f"- **Small sample.** {n_skills} questions, and {cfg.repeats} tries at "
        "each step. Enough to see a ladder fall off a cliff, not enough for "
        "precise percentages."
    )
    add(
        "- **It's evidence, not proof.** A sudden jump at a hint strongly "
        "suggests that hint carried the answer. Read the ladder itself before "
        "acting on it."
    )
    add(
        "- **The student is a model, not a child.** It runs with reasoning "
        "turned off to sit closer to a struggling learner, but it's a stand-in."
    )
    add(
        "- **The marking is done by an AI too.** When an answer isn't an exact "
        "match, another AI decides whether it means the same thing. It never "
        "sees the hints, but it can still get things wrong."
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
