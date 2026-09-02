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
- Converts findings to PR annotations with `scripts/emit_annotations.py`
- Fails the job when findings include `error`/`blocker` severity
- Uploads `custom-check-report.json` as an artifact

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

`scripts/emit_annotations.py` reads this JSON and emits GitHub Actions annotations.

## Required Status Check Setup

To require the PR check before merge:
1. Open repository **Settings**.
2. Go to **Branches** and edit the default branch protection rule.
3. Enable required status checks.
4. Select the **PR Check / pr-check** check.
5. Save the rule.
