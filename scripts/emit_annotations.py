#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit GitHub Actions annotations from custom check report.")
    parser.add_argument("--input", required=True, help="Path to findings JSON")
    parser.add_argument("--summary-file", help="Path to $GITHUB_STEP_SUMMARY")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit non-zero when error findings exist")
    return parser.parse_args()


def escape_annotation(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def write_summary(report: dict, summary_file: Path) -> None:
    summary = report.get("summary", {})
    findings = report.get("findings", [])

    lines = [
        "## Custom Check Summary",
        "",
        f"- Scanned files: {len(report.get('scanned_files', []))}",
        f"- Total findings: {summary.get('total', 0)}",
        f"- Errors: {summary.get('errors', 0)}",
        f"- Warnings: {summary.get('warnings', 0)}",
        "",
    ]

    if findings:
        lines.extend([
            "### Top findings",
            "",
            "| Severity | Rule | File | Line | Message |",
            "| --- | --- | --- | ---: | --- |",
        ])
        for finding in findings[:20]:
            lines.append(
                "| {severity} | {rule} | `{file}` | {line} | {message} |".format(
                    severity=finding.get("severity", ""),
                    rule=finding.get("rule", ""),
                    file=finding.get("file", ""),
                    line=finding.get("line", ""),
                    message=str(finding.get("message", "")).replace("|", "\\|"),
                )
            )

    summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
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

    print(f"Custom check findings: errors={error_count}, warnings={warning_count}")

    if args.summary_file:
        write_summary(report, Path(args.summary_file))

    if args.fail_on_error and error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
