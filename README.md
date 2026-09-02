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
- Runs `scripts/ai_review_check.py`, which calls an Azure AI Foundry agent to review the diff for bugs, security issues, and coding-standard violations
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

## AI Review Check (Azure AI Foundry)

`scripts/ai_review_check.py` sends the PR's unified diff to a pre-deployed Azure AI Foundry agent and asks it to review for:
- bugs / logic errors
- security concerns
- coding-standard / design-principle violations

The agent's response is expected to be a JSON object with a `findings` array using the same schema as `custom_check.py` (`file`, `line`, `severity`, `rule`, `message`, `suggestion`). If the Foundry call fails for any reason (auth, network, timeout, unparsable response), the script does not fail the job — it instead reports the failure as a single `warning` finding so a transient AI-service outage never blocks a PR by itself.

### Required configuration

Set these as repository/organization **Variables** (`vars.*`) unless noted otherwise:
- `AZURE_AI_FOUNDRY_PROJECT_ENDPOINT` — Foundry project endpoint URL
- `AZURE_AI_FOUNDRY_AGENT_ID` — ID of the pre-deployed agent to call

Authentication (choose one):
- **OIDC (recommended)** — set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as Variables and configure a federated credential on the Azure AD app for this repository/workflow. The workflow logs in via `azure/login@v2` and the script authenticates with `DefaultAzureCredential`.
- **API key** — set `AZURE_AI_FOUNDRY_API_KEY` as a repository **Secret**. When present, it takes precedence over OIDC.

## Required Status Check Setup

To require the PR check before merge:
1. Open repository **Settings**.
2. Go to **Branches** and edit the default branch protection rule.
3. Enable required status checks.
4. Select the **PR Check / pr-check** check.
5. Save the rule.
