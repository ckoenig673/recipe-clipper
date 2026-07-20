# Contributing to Recipe Clipper

## Scope

Keep contributions tightly scoped to a single change or bug fix. Do not include unrelated cleanup, opportunistic refactors, or backlog work that is not part of the pull request.

## Branch Workflow

- Branch from `main`.
- Use a short-lived feature or fix branch for each change.
- Keep pull requests focused and reviewable.
- Rebase or merge `main` as needed before opening or updating a pull request.

## Change Expectations

- Follow the existing V1 architecture and service boundaries.
- Prefer small, focused changes over broad rewrites.
- Do not guess behavior; follow existing patterns unless the change explicitly requires otherwise.
- Do not add speculative abstractions or cleanup-only refactors.
- Keep runtime configuration in `.env` and `.env.example`.
- Do not make Ollama a required dependency.
- Do not include secrets, private hostnames, internal IPs, machine-specific paths, or personal data in code, tests, fixtures, or documentation.

## Allowed And Disallowed Changes

Allowed contribution types:

- Focused frontend or backend fixes
- Test, fixture, and test-utility updates
- Standalone scripts and tooling that support the current workflow
- UX polish and service health improvements
- Non-breaking documentation and configuration cleanup

Avoid these changes unless the work explicitly calls for them:

- Websocket systems, Redis/Celery/Kafka queues, or other orchestration redesigns
- Parser behavior changes made casually or with fabricated outputs
- AI review architecture redesigns or any change that makes Ollama mandatory
- Breaking schema changes or casual database migrations
- Large cleanup refactors that are not required by the change

## Validation

Run the relevant validation commands before opening a pull request.

Backend:

```bash
pytest backend/tests/
```

Frontend / Playwright:

```bash
npm run test:e2e
```

If you need an interactive browser session while debugging:

```bash
npm run test:e2e:headed
```

If your change only affects documentation, note that in the pull request description.

Run `docker compose config` for Docker or environment-surface changes.

If the request is validation-only or explicitly says not to change code:

- Do not modify files, create files, or refactor code.
- Run `pytest backend/tests/`.
- Run `npm run test:e2e` when frontend or import flows are relevant.
- Report the exact commands, pass/fail status, failing tests, and likely root cause.

For implementation changes involving backend logic, parsing, fixtures, imports, frontend flows, Docker/config, or scripts, run the relevant validation before considering the work complete.

If tests fail:

1. Identify the root cause.
2. Fix tests, fixtures, or test utilities when the failure is isolated there.
3. If the failure appears to be a production issue, report it clearly instead of hiding it in an unrelated change.

Do not claim success without validation.

## Fixture Guidance

- Prefer real saved HTML for parser fixtures.
- Clearly label and document any temporary stub fixture.
- Do not fabricate parser output.
- Keep fixtures aligned with realistic parser and non-AI pipeline behavior.
- See [Good fixture guidelines](docs/development/good-fixture-guidelines.md).

## Pull Request Guidelines

- Describe the user-facing or developer-facing change clearly.
- Summarize the validation you ran and the outcome.
- Call out limitations, follow-up work, or known risks.
- Keep unrelated file changes out of the pull request.
- If a test is intentionally not run, explain why.

## Review Guidance

- Contributions should preserve existing behavior unless the change explicitly targets that behavior.
- Avoid speculative abstractions and large cleanup passes.
- If a production issue is discovered while validating a change, report it clearly instead of hiding it inside an unrelated pull request.
