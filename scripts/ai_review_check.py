#!/usr/bin/env python3
"""Run an AI-based code review check using an Azure AI Foundry agent.

Unlike scripts/custom_check.py, this script does not compute the diff
itself. The pre-deployed Foundry agent (e.g. Microsoft's
"pr-review-merge-assistant") is configured with its own GitHub connection
(a PAT) and its GitHub tool, so it reads the pull request directly from
GitHub. This script only needs to tell the agent which PR to look at, wait
for its run to complete, and convert its response into the same findings
JSON schema used by ``scripts/custom_check.py`` so that
``scripts/emit_annotations.py`` can turn it into PR annotations without any
further changes.

Authentication (to call the Foundry project/agent API):
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
import sys
import time
from pathlib import Path

RULE = "ai-review"
RUN_POLL_INTERVAL_SECONDS = 2
RUN_TIMEOUT_SECONDS = 300

# The agent already has its own review instructions (risk triage, standards
# check, etc.) configured in Foundry. This message just tells it which PR to
# look at via its GitHub tool, and additionally asks it to also include a
# machine-readable findings block so this script can turn results into PR
# annotations. If the agent ignores this and replies in its own format, the
# response is still surfaced to reviewers as a single finding (see
# build_fallback_finding()).
USER_MESSAGE_TEMPLATE = """Please review this pull request using your GitHub tool: {repo}#{pr_number}
({pr_url})

After your normal review, ALSO append a fenced ```json code block containing
ONLY a JSON object with this schema, listing concrete issues you found:
{{
  "findings": [
    {{
      "file": "path/relative/to/repo",
      "line": 1,
      "severity": "error" | "warning",
      "rule": "ai-review",
      "message": "short description of the issue",
      "suggestion": "concrete suggestion to fix it"
    }}
  ]
}}
Use "error" only for bugs or security issues that should block merging.
If you find no issues, use {{"findings": []}}.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask a Foundry agent (with its own GitHub PAT) to review a PR and output JSON findings."
    )
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. ihcomega56/bookshelf-en-actions")
    parser.add_argument("--pr-number", required=True, help="Pull request number.")
    parser.add_argument("--pr-url", required=True, help="Pull request URL.")
    parser.add_argument("--output", required=True, help="Path to output JSON report.")
    return parser.parse_args()


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
    # Prefer a fenced ```json block if present, since the agent's normal
    # narrative review may surround it with prose.
    fence_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Could not locate a JSON findings block in the agent response.")


def call_foundry_agent(repo: str, pr_number: str, pr_url: str) -> str:
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

    user_message = USER_MESSAGE_TEMPLATE.format(repo=repo, pr_number=pr_number, pr_url=pr_url)

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


def build_fallback_finding(response_text: str) -> list[dict]:
    """Used when the agent replied but not with a parseable JSON findings block.

    Surfaces the agent's full narrative review as a single informational
    finding rather than silently discarding it.
    """
    snippet = response_text.strip()
    if len(snippet) > 2000:
        snippet = snippet[:2000] + " ... [truncated]"
    return [
        {
            "file": "",
            "line": 1,
            "severity": "warning",
            "rule": "ai-review-narrative",
            "message": "Agent responded without a parseable JSON findings block; see full review below.",
            "suggestion": snippet,
        }
    ]


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        response_text = call_foundry_agent(args.repo, args.pr_number, args.pr_url)
        try:
            raw = extract_json_object(response_text)
            findings = normalize_findings(raw)
        except (ValueError, json.JSONDecodeError):
            findings = build_fallback_finding(response_text)
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
        "scanned_files": [],
        "findings": findings,
        "summary": {"total": len(findings), "errors": errors, "warnings": warnings},
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"AI review findings: total={len(findings)}, errors={errors}, warnings={warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
