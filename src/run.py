"""Entry point. One command, end to end.

python -m src.run --mock          # no API key needed, deterministic
python -m src.run                 # real run, needs GEMINI_API_KEY in .env
python -m src.run --skills 4      # quick real run over four standards
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .client import ModelClient
from .config import RESULTS, ROOT, Config
from .detect import detect_all, summarise
from .generate import build_items, load_skills
from .report import DARK, LIGHT, draw_chart, write_findings
from .schemas import RunReport
from .simulate import HINTS_ONLY, WITH_QUESTION, build_curves, sweep
from .tag import check_drift

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
)
log = logging.getLogger("hintladder")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Socratic hint-ladder leakage harness")
    p.add_argument(
        "--mock",
        action="store_true",
        help="run the deterministic simulator instead of calling Gemini",
    )
    p.add_argument(
        "--skills", type=int, default=None, help="cap the number of standards"
    )
    p.add_argument(
        "--repeats", type=int, default=None, help="student attempts per cell"
    )
    p.add_argument(
        "--languages",
        type=str,
        default=None,
        help="comma-separated, e.g. en,es,fr (en is always the base)",
    )
    p.add_argument(
        "--student", type=str, default=None, help="override the student model"
    )
    p.add_argument("--no-cache", action="store_true", help="ignore the on-disk cache")
    p.add_argument(
        "--no-drift", action="store_true", help="skip the standards-drift check"
    )
    p.add_argument(
        "--with-question",
        action="store_true",
        help=(
            "also run the secondary sweep that shows the student the question; "
            "doubles the student calls and produces flat curves on current "
            "models (see the note at the top of simulate.py)"
        ),
    )
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    cfg = Config(mock=args.mock)
    if args.skills is not None:
        cfg = cfg.model_copy(update={"skills_limit": args.skills})
    if args.repeats is not None:
        cfg = cfg.model_copy(update={"repeats": args.repeats})
    if args.languages:
        langs = [x.strip() for x in args.languages.split(",") if x.strip()]
        if "en" not in langs:
            langs.insert(0, "en")
        cfg = cfg.model_copy(update={"languages": langs})
    if args.student:
        cfg = cfg.model_copy(update={"student_model": args.student})
    if args.no_cache:
        cfg = cfg.model_copy(update={"use_cache": False})
    return cfg


async def run(
    cfg: Config, do_drift: bool = True, conditions: list[str] | None = None
) -> RunReport:
    conditions = conditions or [HINTS_ONLY]
    client = ModelClient(cfg)
    skills = load_skills(cfg)

    log.info(
        "Writing items for %s standards in %s", len(skills), ", ".join(cfg.languages)
    )
    items = await build_items(client, cfg)

    cells = len(items) * (cfg.max_hint_level + 1) * cfg.repeats * len(conditions)
    log.info(
        "Sweeping %s ladders in %s (%s attempts)",
        len(items),
        " + ".join(conditions),
        cells,
    )
    attempts = await sweep(client, cfg, items, skills, conditions)

    curves = build_curves(cfg, items, attempts, conditions)
    detections = detect_all(curves, cfg)

    checks = []
    if do_drift:
        log.info(
            "Re-tagging %s English items blind", sum(i.language == "en" for i in items)
        )
        checks = await check_drift(client, cfg, items, skills)

    return RunReport(
        mock=cfg.mock,
        curves=curves,
        detections=detections,
        tag_checks=checks,
        costs=client.costs(),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = build_config(args)

    conditions = [HINTS_ONLY] + ([WITH_QUESTION] if args.with_question else [])
    report = asyncio.run(run(cfg, do_drift=not args.no_drift, conditions=conditions))

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "run.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    # The chart shows the primary measurement only.
    primary = [c for c in report.curves if c.condition == HINTS_ONLY]
    primary_dets = [d for d in report.detections if d.condition == HINTS_ONLY]
    chart = draw_chart(primary, primary_dets, cfg, ROOT / "leakage_curves.png", LIGHT)
    draw_chart(primary, primary_dets, cfg, ROOT / "leakage_curves_dark.png", DARK)
    findings = write_findings(report, cfg, chart)

    counts = summarise(report.detections)
    print()
    print(
        f"  {counts.get('leaked', 0)} of {len(report.detections)} ladders leaked early"
    )
    print(f"  outcomes: {json.dumps(counts)}")
    if report.costs:
        print(f"  spend:    ${report.total_usd:,.4f}")
    elif not cfg.mock:
        print("  spend:    $0, everything came from cache")
    print(f"  chart:    {chart}")
    print(f"  findings: {findings}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
