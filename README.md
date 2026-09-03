# Bookshelf

Bookshelf is a Spring Boot demo application for managing books and loans in an internal library.

## Tech Stack

- Java 21
- Spring Boot 3.5 (Web, Data JPA, Validation)
- Gradle (wrapper included)
- H2 in-memory database
- JUnit 5, AssertJ, MockMvc

## Features

- List books and search by title
- Get book details
- Register books
- Borrow books
- Return books
- Renew loan due dates
- List overdue loans
- Preview overdue reminder messages

## API Endpoints

- `GET /api/books?keyword=`
- `GET /api/books/{id}`
- `POST /api/books`
- `POST /api/loans/books/{bookId}`
- `POST /api/loans/{loanId}/return`
- `POST /api/loans/{loanId}/renew`
- `GET /api/loans/overdue`
- `GET /api/loans/overdue/reminder-preview`

## Build and Test

```bash
./gradlew build
```

## Run

```bash
./gradlew bootRun
```

The app starts at `http://localhost:8080`.

## GitHub Actions Workflows

### 1) PR Check (`.github/workflows/pr-check.yml`)

Trigger:
- `pull_request` (`opened`, `synchronize`, `reopened`) when the PR targets the default branch

What it does:
- Checks out full git history
- Builds and runs tests (`./gradlew build`)
- Computes changed files from PR base/head diff
- Runs `scripts/custom_check.py` against changed files
- Runs `scripts/ai_review_check.py`, which asks a pre-deployed Azure AI Foundry agent to review the PR (via its own GitHub PAT/tool) for bugs, security issues, and coding-standard violations
- Converts findings from both checks to PR annotations with `scripts/emit_annotations.py`
- Fails the job when findings include `error`/`blocker` severity
- Uploads `custom-check-report.json` and `ai-review-report.json` as artifacts

### 2) Post Merge Check (`.github/workflows/post-merge-check.yml`)

Trigger:
- `push` to repository branches, with the job running only when the pushed branch is the default branch

What it does:
- Checks out full history
- Builds and runs tests (`./gradlew build`)
- Runs `scripts/custom_check.py` over the full repository
- Writes summary to the job summary and emits annotations
- Uploads `full-repo-check-report.json` as an artifact

### 3) Scheduled Check (`.github/workflows/scheduled-check.yml`)

Trigger:
- Daily schedule (`0 2 * * *`)
- Manual run (`workflow_dispatch`)

What it does:
- Checks out full history
- Runs dependency check task when configured; otherwise records a fallback dependency snapshot
- Runs `scripts/custom_check.py` over the full repository
- Writes summary to the job summary and emits annotations
- Uploads check reports as artifacts

## Custom Check Script

`scripts/custom_check.py` produces JSON findings with:
- file path
- line number
- severity
- rule
- message
- suggestion

Current rule coverage includes:
- potential hardcoded secrets
- unsafe deserialization usage
- SQL string concatenation patterns
- TODO/FIXME markers
- long methods
- deep nesting
- duplicated code-line heuristics

`scripts/emit_annotations.py` reads this JSON and emits GitHub Actions annotations. It accepts one or more `--input` reports (merging them) so both the deterministic and AI-based checks can be combined into a single set of annotations.

It also (optionally) renders human-friendly, severity-annotated output:
- `--summary-file "$GITHUB_STEP_SUMMARY"` — writes a findings table to the workflow run's Step Summary page.
- `--pr-comment-file pr-comment.md` — writes a PR-comment-ready markdown file: a 🔴/🟡 severity count header, a pass/fail status line, and a collapsible findings table (each row also tagged with its source, `🔍 Custom check` or `🤖 AI review`). Pass `--ai-raw-file <path>` to additionally embed the AI agent's full narrative response in its own collapsible section at the bottom.

GitHub Markdown has no native cell coloring, so 🔴 (error/blocker) and 🟡 (warning) emoji are used consistently across the Step Summary and PR comment as a readable stand-in for color-coding.

## AI Review Check (Azure AI Foundry)

`scripts/ai_review_check.py` asks a pre-deployed Azure AI Foundry agent (e.g. Microsoft's `pr-review-merge-assistant`) to review the PR for:
- bugs / logic errors
- security concerns
- coding-standard / design-principle violations

The agent is configured in Foundry with its own **GitHub connection (a PAT) and GitHub tool**, so it reads the pull request directly from GitHub — this script only passes the repository name, PR number, and PR URL, and asks the agent to also append a fenced ```` ```json ```` block with a `findings` array using the same schema as `custom_check.py` (`file`, `line`, `severity`, `rule`, `message`, `suggestion`).

If the agent replies without a parseable JSON block (e.g. it only returns its own narrative risk/summary/recommendation format), its full response is surfaced as a single informational finding instead of being discarded. If the Foundry call fails for any reason (auth, network, timeout), the script does not fail the job — it instead reports the failure as a single `warning` finding so a transient AI-service outage never blocks a PR by itself.

### Required configuration

Set these as repository/organization **Variables** (`vars.*`) unless noted otherwise:
- `AZURE_AI_FOUNDRY_PROJECT_ENDPOINT` — Foundry **project** endpoint URL, in the form
  `https://<resource>.services.ai.azure.com/api/projects/<project-name>`
  (the plain `https://<resource>.cognitiveservices.azure.com/` resource endpoint does *not* work with the agent-invocation API used here).
- `AZURE_AI_FOUNDRY_AGENT_ID` — ID of the pre-deployed agent to call (the `id` field of the agent's manifest, e.g. `pr-review-merge-assistant-2`; not the Entra Agent Identity / `agent_guid`).

Authentication for calling the Foundry project/agent API (choose one — this is separate from the GitHub PAT configured on the agent's GitHub connection, which lets the agent read PRs):
- **OIDC (recommended)** — set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as Variables and configure a federated credential on the Azure AD app for this repository/workflow. The workflow logs in via `azure/login@v2` and the script authenticates with `DefaultAzureCredential`. Required if the Foundry resource enforces `disableLocalAuth` (common under an Azure Policy that disallows API keys).
- **API key** — set `AZURE_AI_FOUNDRY_API_KEY` as a repository **Secret**. When present, it takes precedence over OIDC. Not usable if the resource has local (key-based) auth disabled.

### MCP tool approval

The agent's GitHub tool is invoked via MCP (Model Context Protocol). The Responses API requires each MCP tool call to be explicitly approved before it executes (`mcp_approval_request` output items). `call_foundry_agent()` automatically approves these requests in a loop (up to `MAX_APPROVAL_TURNS`) so the agent can read the PR and produce its review without manual intervention.

## Required Status Check Setup

To require the PR check before merge:
1. Open repository **Settings**.
2. Go to **Branches** and edit the default branch protection rule.
3. Enable required status checks.
4. Select the **PR Check / pr-check** check.
5. Save the rule.
