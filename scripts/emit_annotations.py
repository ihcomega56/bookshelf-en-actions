#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

# Severity -> emoji, used consistently across the Step Summary table and the
# PR comment so results are scannable at a glance (GitHub Markdown has no
# native cell coloring, so emoji is the closest practical substitute).
SEVERITY_ICON = {
    "error": "🔴",
    "blocker": "🔴",
    "warning": "🟡",
}
DEFAULT_ICON = "⚪"

SOURCE_LABEL = {
    "ai-review": "🤖 AI review",
}
DEFAULT_SOURCE_LABEL = "🔍 Custom check"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit GitHub Actions annotations from custom check report(s).")
    parser.add_argument(
        "--input",
        required=True,
        action="append",
        help="Path to findings JSON. May be given multiple times to merge several reports.",
    )
    parser.add_argument("--summary-file", help="Path to $GITHUB_STEP_SUMMARY")
    parser.add_argument(
        "--pr-comment-file",
        help="Write a PR-comment-ready markdown file (severity-annotated findings table) to this path.",
    )
    parser.add_argument(
        "--ai-raw-file",
        help="Optional path to the AI reviewer's raw narrative response; embedded as a collapsible "
        "section at the bottom of --pr-comment-file if provided.",
    )
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero when error findings exist")
    return parser.parse_args()


def severity_icon(severity: str) -> str:
    return SEVERITY_ICON.get(severity, DEFAULT_ICON)


def source_label(finding: dict) -> str:
    return SOURCE_LABEL.get(finding.get("_source_mode"), DEFAULT_SOURCE_LABEL)


def load_reports(paths: list[str]) -> dict:
    """Merge one or more findings reports into a single report dict."""
    merged_scanned_files: set[str] = set()
    merged_findings: list[dict] = []
    modes: list[str] = []

    for path in paths:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        merged_scanned_files.update(report.get("scanned_files", []))
        mode = report.get("mode")
        for finding in report.get("findings", []):
            # Tag each finding with which report/check produced it, so the
            # PR comment and summary can label rows (e.g. "🤖 AI review" vs
            # "🔍 Custom check") without changing the on-disk JSON schema.
            finding = {**finding, "_source_mode": mode}
            merged_findings.append(finding)
        if mode:
            modes.append(mode)

    errors = sum(1 for f in merged_findings if f.get("severity") in {"error", "blocker"})
    warnings = sum(1 for f in merged_findings if f.get("severity") == "warning")

    return {
        "mode": "+".join(modes) if modes else None,
        "scanned_files": sorted(merged_scanned_files),
        "findings": merged_findings,
        "summary": {"total": len(merged_findings), "errors": errors, "warnings": warnings},
    }


def escape_annotation(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def sorted_by_severity(findings: list[dict]) -> list[dict]:
    # Show blockers/errors first, then warnings, then anything else.
    rank = {"error": 0, "blocker": 0, "warning": 1}
    return sorted(findings, key=lambda f: rank.get(f.get("severity", ""), 2))


def build_findings_table(findings: list[dict], limit=None) -> list[str]:
    rows = [
        "| Severity | Source | Rule | File | Line | Message |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    shown = findings[:limit] if limit else findings
    for finding in shown:
        rows.append(
            "| {icon} {severity} | {source} | {rule} | `{file}` | {line} | {message} |".format(
                icon=severity_icon(finding.get("severity", "")),
                severity=finding.get("severity", ""),
                source=source_label(finding),
                rule=finding.get("rule", ""),
                file=finding.get("file", ""),
                line=finding.get("line", ""),
                message=str(finding.get("message", "")).replace("|", "\\|").replace("\n", " "),
            )
        )
    if limit and len(findings) > limit:
        rows.append(f"\n_...and {len(findings) - limit} more finding(s); see the full report artifact._")
    return rows


def write_summary(report: dict, summary_file: Path) -> None:
    summary = report.get("summary", {})
    findings = sorted_by_severity(report.get("findings", []))
    errors = summary.get("errors", 0)
    warnings = summary.get("warnings", 0)

    lines = [
        "## PR Checks Summary",
        "",
        f"- Scanned files: {len(report.get('scanned_files', []))}",
        f"- Total findings: {summary.get('total', 0)}",
        f"- {severity_icon('error')} Errors: {errors}",
        f"- {severity_icon('warning')} Warnings: {warnings}",
        "",
    ]

    if findings:
        lines.append("### Findings")
        lines.append("")
        lines.extend(build_findings_table(findings, limit=20))
        lines.append("")

    summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pr_comment(report: dict, comment_file: Path, ai_raw_file) -> None:
    summary = report.get("summary", {})
    findings = sorted_by_severity(report.get("findings", []))
    errors = summary.get("errors", 0)
    warnings = summary.get("warnings", 0)

    status_line = (
        f"❌ **{errors} blocking issue(s) found** — this check will fail."
        if errors
        else "✅ No blocking issues found."
    )

    lines = [
        "## 🧪 PR Check Results",
        "",
        f"{severity_icon('error')} **{errors}** error(s)  ·  {severity_icon('warning')} **{warnings}** warning(s)  ·  {summary.get('total', 0)} total",
        "",
        status_line,
        "",
    ]

    if findings:
        lines.append("<details>")
        lines.append(f"<summary>Show {len(findings)} finding(s)</summary>")
        lines.append("")
        lines.extend(build_findings_table(findings, limit=30))
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if ai_raw_file:
        raw_path = Path(ai_raw_file)
        if raw_path.exists():
            raw_text = raw_path.read_text(encoding="utf-8").strip()
            if raw_text:
                lines.append("<details>")
                lines.append("<summary>🤖 Full AI reviewer narrative</summary>")
                lines.append("")
                lines.append(raw_text)
                lines.append("")
                lines.append("</details>")
                lines.append("")

    comment_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report = load_reports(args.input)
    findings = report.get("findings", [])

    error_count = 0
    warning_count = 0
    for finding in findings:
        severity = finding.get("severity", "warning")
        message = f"[{finding.get('rule', 'custom-check')}] {finding.get('message', '')} Suggestion: {finding.get('suggestion', '')}"
        escaped = escape_annotation(message)
        file_name = finding.get("file", "")
        line_number = finding.get("line", 1)

        if severity in {"error", "blocker"}:
            error_count += 1
            print(f"::error file={file_name},line={line_number}::{escaped}")
        else:
            warning_count += 1
            print(f"::warning file={file_name},line={line_number}::{escaped}")

    print(f"Check findings: errors={error_count}, warnings={warning_count}")

    if args.summary_file:
        write_summary(report, Path(args.summary_file))

    if args.pr_comment_file:
        write_pr_comment(report, Path(args.pr_comment_file), args.ai_raw_file)

    if args.fail_on_error and error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
