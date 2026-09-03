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
from pathlib import Path

RULE = "ai-review"
RUN_TIMEOUT_SECONDS = 300
MAX_APPROVAL_TURNS = 10

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
    parser.add_argument(
        "--raw-output",
        help="Optional path to also save the agent's raw narrative response (for posting as a PR comment).",
    )
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

    # allow_preview=True is required to target a specific agent's endpoint
    # (agent_name below) rather than a generic project-level deployment.
    project_client = AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True)
    openai_client = project_client.get_openai_client(agent_name=agent_id)

    user_message = USER_MESSAGE_TEMPLATE.format(repo=repo, pr_number=pr_number, pr_url=pr_url)

    response = openai_client.responses.create(input=user_message, timeout=RUN_TIMEOUT_SECONDS)

    # The agent's GitHub MCP tool requires explicit approval before each tool
    # call actually executes (a security feature of the Responses API's MCP
    # integration). Auto-approve these requests in a loop -- we already trust
    # this pre-deployed agent and its GitHub connection -- until the agent
    # produces a final message with no more pending approvals.
    for _ in range(MAX_APPROVAL_TURNS):
        approvals = [item for item in response.output if getattr(item, "type", None) == "mcp_approval_request"]
        if not approvals:
            break
        approval_inputs = [
            {"type": "mcp_approval_response", "approve": True, "approval_request_id": item.id}
            for item in approvals
        ]
        response = openai_client.responses.create(
            input=approval_inputs,
            previous_response_id=response.id,
            timeout=RUN_TIMEOUT_SECONDS,
        )

    if getattr(response, "status", None) not in (None, "completed"):
        raise RuntimeError(f"Foundry agent run did not complete successfully (status={response.status}).")

    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("Foundry agent run completed but returned no output text (possibly stuck on MCP tool approval).")
    return output_text


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
    raw_output_path = Path(args.raw_output) if args.raw_output else None
    if raw_output_path:
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        response_text = call_foundry_agent(args.repo, args.pr_number, args.pr_url)
        if raw_output_path:
            raw_output_path.write_text(response_text, encoding="utf-8")
        try:
            raw = extract_json_object(response_text)
            findings = normalize_findings(raw)
        except (ValueError, json.JSONDecodeError):
            findings = build_fallback_finding(response_text)
    except Exception as exc:  # noqa: BLE001 - convert any failure into a warning finding
        report = build_empty_report(f"AI review check failed: {exc}", severity="warning")
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if raw_output_path:
            raw_output_path.write_text(f"AI review check failed: {exc}", encoding="utf-8")
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
