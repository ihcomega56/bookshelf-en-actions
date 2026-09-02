#!/usr/bin/env python3
"""Run an AI-based code review check using an Azure AI Foundry agent.

This script sends the PR diff to a pre-deployed Azure AI Foundry agent and
converts the agent's response into the same findings JSON schema used by
``scripts/custom_check.py`` so that ``scripts/emit_annotations.py`` can turn
it into PR annotations without any further changes.

Authentication:
    - If ``AZURE_AI_FOUNDRY_API_KEY`` is set, an ``AzureKeyCredential`` is used.
    - Otherwise ``DefaultAzureCredential`` is used, which supports GitHub
      Actions OIDC federation via ``azure/login`` as well as local
      developer credentials.

Required configuration (environment variables):
    - ``AZURE_AI_FOUNDRY_PROJECT_ENDPOINT``: Foundry project endpoint URL.
    - ``AZURE_AI_FOUNDRY_AGENT_ID``: ID of the pre-deployed agent to call.

If the Foundry call fails for any infrastructure reason (auth, network,
timeout, unparsable response), the script does not raise -- it instead
emits a single ``warning`` finding describing the failure so that a
transient AI-service outage does not unexpectedly block PRs whose only
issue is the AI check being unavailable.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RULE = "ai-review"
MAX_DIFF_CHARS = 60_000
RUN_POLL_INTERVAL_SECONDS = 2
RUN_TIMEOUT_SECONDS = 300

SYSTEM_PROMPT = """You are an expert code reviewer for a Java/Spring Boot repository.
Review the provided unified diff and report only genuine issues in these categories:
1. Bugs or logic errors
2. Security concerns
3. Violations of common coding standards / design principles

Respond with ONLY a JSON object (no markdown fences, no prose) matching this schema:
{
  "findings": [
    {
      "file": "path/relative/to/repo",
      "line": 1,
      "severity": "error" | "warning",
      "rule": "ai-review",
      "message": "short description of the issue",
      "suggestion": "concrete suggestion to fix it"
    }
  ]
}
Use "error" severity only for bugs or security issues that should block merging.
Use "warning" for style/design-principle concerns.
If you find no issues, return {"findings": []}.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an AI review check via Azure AI Foundry and output JSON findings.")
    parser.add_argument("--changed-files-file", required=True, help="Path to file containing changed files, one per line.")
    parser.add_argument("--base-sha", required=True, help="Base commit SHA for the diff.")
    parser.add_argument("--head-sha", required=True, help="Head commit SHA for the diff.")
    parser.add_argument("--output", required=True, help="Path to output JSON report.")
    parser.add_argument("--base-dir", default=".", help="Repository root.")
    return parser.parse_args()


def read_changed_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_diff(base_dir: Path, base_sha: str, head_sha: str, changed_files: list[str]) -> str:
    if not changed_files:
        return ""
    cmd = ["git", "diff", f"{base_sha}...{head_sha}", "--"] + changed_files
    result = subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True, check=False)
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... [diff truncated for length] ..."
    return diff


def build_empty_report(reason: str, severity: str = "warning") -> dict:
    findings = []
    if reason:
        findings.append(
            {
                "file": "",
                "line": 1,
                "severity": severity,
                "rule": "ai-review-unavailable",
                "message": reason,
                "suggestion": "Re-run the AI check, or investigate Foundry connectivity/configuration.",
            }
        )
    errors = sum(1 for f in findings if f["severity"] in {"error", "blocker"})
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "mode": "ai-review",
        "scanned_files": [],
        "findings": findings,
        "summary": {"total": len(findings), "errors": errors, "warnings": warnings},
    }


def extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Could not locate a JSON object in the agent response.")


def call_foundry_agent(diff_text: str, changed_files: list[str]) -> str:
    from azure.ai.projects import AIProjectClient

    endpoint = os.environ["AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"]
    agent_id = os.environ["AZURE_AI_FOUNDRY_AGENT_ID"]
    api_key = os.environ.get("AZURE_AI_FOUNDRY_API_KEY")

    if api_key:
        from azure.core.credentials import AzureKeyCredential

        credential = AzureKeyCredential(api_key)
    else:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()

    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    agents_client = project_client.agents

    user_message = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Changed files:\n{chr(10).join(changed_files)}\n\n"
        f"Unified diff:\n```diff\n{diff_text}\n```"
    )

    thread = agents_client.threads.create()
    agents_client.messages.create(thread_id=thread.id, role="user", content=user_message)
    run = agents_client.runs.create(thread_id=thread.id, agent_id=agent_id)

    deadline = time.time() + RUN_TIMEOUT_SECONDS
    while run.status in {"queued", "in_progress", "requires_action"}:
        if time.time() > deadline:
            raise TimeoutError(f"Foundry agent run timed out after {RUN_TIMEOUT_SECONDS}s (status={run.status}).")
        time.sleep(RUN_POLL_INTERVAL_SECONDS)
        run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)

    if run.status != "completed":
        raise RuntimeError(f"Foundry agent run did not complete successfully (status={run.status}).")

    messages = agents_client.messages.list(thread_id=thread.id)
    for message in messages:
        if message.role == "assistant":
            parts = getattr(message, "content", []) or []
            texts = []
            for part in parts:
                text_value = getattr(getattr(part, "text", None), "value", None)
                if text_value:
                    texts.append(text_value)
            if texts:
                return "\n".join(texts)

    raise RuntimeError("Foundry agent run completed but returned no assistant message.")


def normalize_findings(raw: dict) -> list[dict]:
    findings = []
    for item in raw.get("findings", []):
        file_path = str(item.get("file", "") or "")
        severity = item.get("severity", "warning")
        if severity not in {"error", "warning", "blocker"}:
            severity = "warning"
        findings.append(
            {
                "file": file_path,
                "line": int(item.get("line", 1) or 1),
                "severity": severity,
                "rule": item.get("rule", RULE) or RULE,
                "message": str(item.get("message", "")),
                "suggestion": str(item.get("suggestion", "")),
            }
        )
    return findings


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    changed_files = read_changed_files(Path(args.changed_files_file))
    if not changed_files:
        output_path.write_text(json.dumps(build_empty_report(""), indent=2), encoding="utf-8")
        print("No changed files to review with AI check.")
        return 0

    diff_text = collect_diff(base_dir, args.base_sha, args.head_sha, changed_files)
    if not diff_text.strip():
        output_path.write_text(json.dumps(build_empty_report(""), indent=2), encoding="utf-8")
        print("Empty diff; skipping AI review call.")
        return 0

    try:
        response_text = call_foundry_agent(diff_text, changed_files)
        raw = extract_json_object(response_text)
        findings = normalize_findings(raw)
    except Exception as exc:  # noqa: BLE001 - convert any failure into a warning finding
        report = build_empty_report(f"AI review check failed: {exc}", severity="warning")
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"AI review check failed: {exc}", file=sys.stderr)
        return 0

    findings.sort(key=lambda item: (item["file"], item["line"], item["severity"], item["rule"]))
    errors = sum(1 for f in findings if f["severity"] in {"error", "blocker"})
    warnings = sum(1 for f in findings if f["severity"] == "warning")

    report = {
        "mode": "ai-review",
        "scanned_files": sorted(set(changed_files)),
        "findings": findings,
        "summary": {"total": len(findings), "errors": errors, "warnings": warnings},
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"AI review findings: total={len(findings)}, errors={errors}, warnings={warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
