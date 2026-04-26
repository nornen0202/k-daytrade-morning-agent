from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from daytrade_agent.config import AppConfig
from daytrade_agent.render.markdown import markdown_to_html
from daytrade_agent.storage.report_store import discover_reports


def build_site(config: AppConfig) -> list[Path]:
    reports = discover_reports(config.content_dir)
    dist = config.dist_dir
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reports").mkdir(parents=True, exist_ok=True)
    (dist / "assets").mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(config.site_templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    created: list[Path] = []
    latest = reports[0] if reports else None
    created.append(
        _render(
            env,
            "index.html",
            dist / "index.html",
            latest=latest,
            reports=reports[:10],
            config=config,
        )
    )
    created.append(
        _render(
            env,
            "archive.html",
            dist / "reports" / "index.html",
            reports=reports,
            config=config,
        )
    )

    report_template = env.get_template("report.html")
    for report in reports:
        report_date = report["report_date"]
        destination = dist / "reports" / report_date / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            report_template.render(
                report=report,
                report_html=markdown_to_html(report["markdown"]),
                config=config,
            ),
            encoding="utf-8",
        )
        created.append(destination)

    shutil.copyfile(
        config.site_templates_dir / "assets" / "style.css",
        dist / "assets" / "style.css",
    )
    created.append(dist / "assets" / "style.css")
    return created


def _render(env: Environment, template_name: str, path: Path, **context: object) -> Path:
    path.write_text(env.get_template(template_name).render(**context), encoding="utf-8")
    return path
