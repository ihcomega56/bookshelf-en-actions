#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".java",
    ".kt",
    ".kts",
    ".groovy",
    ".gradle",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".properties",
    ".sql",
    ".xml",
    ".sh",
    ".py",
}

PATTERN_RULES = [
    {
        "rule": "hardcoded-secret",
        "severity": "error",
        "pattern": re.compile(
            r"(?i)\b(password|passwd|api[_-]?key|secret|token)\b\s*[:=]\s*[\"'][^\"'\n]{4,}[\"']"
        ),
        "message": "Potential hardcoded secret detected.",
        "suggestion": "Move credentials to encrypted secrets or environment variables.",
    },
    {
        "rule": "unsafe-deserialization",
        "severity": "warning",
        "pattern": re.compile(r"\bObjectInputStream\b|\breadObject\s*\("),
        "message": "Potential unsafe deserialization usage detected.",
        "suggestion": "Avoid deserializing untrusted data, or validate input strictly.",
    },
    {
        "rule": "sql-string-concatenation",
        "severity": "warning",
        "pattern": re.compile(
            r"(?i)(SELECT|INSERT|UPDATE|DELETE)[^\n;]*[\"']\s*\+|\+\s*[\"'][^\n]*(WHERE|FROM|SET)"
        ),
        "message": "Possible SQL string concatenation found.",
        "suggestion": "Use parameterized queries or prepared statements.",
    },
    {
        "rule": "todo-fixme",
        "severity": "warning",
        "pattern": re.compile(r"\b(TODO|FIXME)\b"),
        "message": "TODO/FIXME marker found.",
        "suggestion": "Resolve or track this item before merging when possible.",
    },
]


METHOD_DECLARATION = re.compile(
    r"^\s*(public|protected|private)?\s*(static\s+)?[\w<>,\[\] ?]+\s+\w+\s*\([^;]*\)\s*(throws [^{]+)?\{\s*$"
)
CONTROL_FLOW_PREFIXES = ("if", "for", "while", "switch", "catch", "else", "do", "try", "synchronized")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run custom static checks and output JSON findings.")
    parser.add_argument("--mode", choices=["diff", "full"], default="full")
    parser.add_argument("--changed-files-file", help="Path to file containing changed files, one per line.")
    parser.add_argument("--output", required=True, help="Path to output JSON report.")
    parser.add_argument("--base-dir", default=".", help="Repository root.")
    return parser.parse_args()


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def read_changed_files(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_full_scan_files(base_dir: Path) -> Iterable[str]:
    for file_path in base_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(base_dir)
        if any(part.startswith(".") and part not in {".github"} for part in rel.parts):
            continue
        if "build" in rel.parts or ".gradle" in rel.parts:
            continue
        if is_text_file(file_path):
            yield rel.as_posix()


def add_finding(findings: list[dict], file_path: str, line: int, severity: str, rule: str, message: str, suggestion: str) -> None:
    findings.append(
        {
            "file": file_path,
            "line": line,
            "severity": severity,
            "rule": rule,
            "message": message,
            "suggestion": suggestion,
        }
    )


def scan_line_rules(rel_path: str, lines: list[str], findings: list[dict]) -> None:
    for index, line in enumerate(lines, start=1):
        for rule in PATTERN_RULES:
            if rule["pattern"].search(line):
                add_finding(
                    findings,
                    rel_path,
                    index,
                    rule["severity"],
                    rule["rule"],
                    rule["message"],
                    rule["suggestion"],
                )


def scan_long_methods(rel_path: str, lines: list[str], findings: list[dict]) -> None:
    if not rel_path.endswith(".java"):
        return

    i = 0
    while i < len(lines):
        current = lines[i]
        stripped = current.strip()
        if METHOD_DECLARATION.match(current):
            first_word = stripped.split("(", 1)[0].split()[-1] if stripped else ""
            if first_word in CONTROL_FLOW_PREFIXES:
                i += 1
                continue
            start_line = i + 1
            depth = current.count("{") - current.count("}")
            length = 1
            j = i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                length += 1
                j += 1
            if length > 80:
                add_finding(
                    findings,
                    rel_path,
                    start_line,
                    "warning",
                    "long-method",
                    f"Method length is {length} lines.",
                    "Consider splitting the method into smaller units.",
                )
            i = max(j, i + 1)
            continue
        i += 1


def scan_deep_nesting(rel_path: str, lines: list[str], findings: list[dict]) -> None:
    if not rel_path.endswith(".java"):
        return

    depth = 0
    first_deep_line = None
    max_depth = 0
    for index, line in enumerate(lines, start=1):
        opens = line.count("{")
        closes = line.count("}")
        depth += opens
        if depth > max_depth:
            max_depth = depth
        if depth > 5 and first_deep_line is None:
            first_deep_line = index
        depth -= closes

    if max_depth > 5 and first_deep_line is not None:
        add_finding(
            findings,
            rel_path,
            first_deep_line,
            "warning",
            "deep-nesting",
            f"Nesting depth reaches {max_depth} levels.",
            "Consider simplifying conditional and loop nesting.",
        )


def scan_duplicate_lines(rel_path: str, lines: list[str], findings: list[dict]) -> None:
    if not rel_path.endswith(".java"):
        return

    normalized_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 30:
            continue
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        normalized_lines.append(stripped)

    counts = Counter(normalized_lines)
    for text, count in counts.items():
        if count >= 3:
            for index, line in enumerate(lines, start=1):
                if line.strip() == text:
                    add_finding(
                        findings,
                        rel_path,
                        index,
                        "warning",
                        "duplicate-line",
                        "Potential duplicate logic detected.",
                        "Consider extracting shared logic.",
                    )
                    break


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()

    if args.mode == "diff":
        if not args.changed_files_file:
            raise SystemExit("--changed-files-file is required when --mode diff")
        changed_file_path = Path(args.changed_files_file)
        candidate_files = read_changed_files(changed_file_path)
    else:
        candidate_files = list(iter_full_scan_files(base_dir))

    files_to_scan = []
    for rel in candidate_files:
        candidate = (base_dir / rel).resolve()
        if not candidate.exists() or not candidate.is_file():
            continue
        if base_dir not in candidate.parents and candidate != base_dir:
            continue
        if not is_text_file(candidate):
            continue
        files_to_scan.append(candidate.relative_to(base_dir).as_posix())

    findings: list[dict] = []
    for rel_path in sorted(set(files_to_scan)):
        path = base_dir / rel_path
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = content.splitlines()
        scan_line_rules(rel_path, lines, findings)
        scan_long_methods(rel_path, lines, findings)
        scan_deep_nesting(rel_path, lines, findings)
        scan_duplicate_lines(rel_path, lines, findings)

    findings.sort(key=lambda item: (item["file"], item["line"], item["severity"], item["rule"]))
    errors = sum(1 for f in findings if f["severity"] in {"error", "blocker"})
    warnings = sum(1 for f in findings if f["severity"] == "warning")

    report = {
        "mode": args.mode,
        "scanned_files": sorted(set(files_to_scan)),
        "findings": findings,
        "summary": {
            "total": len(findings),
            "errors": errors,
            "warnings": warnings,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Scanned {len(report['scanned_files'])} files.")
    print(f"Findings: total={len(findings)}, errors={errors}, warnings={warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
