# Release Process

Recipe Clipper uses protected pull requests for release preparation and a deliberate manual step for publishing a GitHub release. Preparing release files does not authorize creating a tag or publishing a release.

## Version Sources

The current application version must agree across:

- `backend/app/main.py` — `/version` API response
- `frontend/app.js` — visible application build label
- `package.json` and `package-lock.json` — repository test tooling metadata
- `.env.example` and `docker-compose.yml` — frontend cache-bust build value
- `CHANGELOG.md` — public change history
- `docs/architecture/README.md` — documented architecture baseline

The Android share companion is versioned independently in `android-share-companion/app/build.gradle.kts`. Recipe Clipper `v1.0.0` includes companion source version `0.2.1`; it does not imply an Android `1.0.0` binary.

Run the consistency check with:

```bash
python scripts/check_release_versions.py
```

## Pre-Publish Checklist

- [ ] The release-preparation pull request is merged into protected `main`.
- [ ] The local checkout is clean and matches `origin/main`.
- [ ] `python scripts/check_release_versions.py` passes.
- [ ] Backend tests pass with Python 3.11.
- [ ] Playwright tests pass against an isolated test deployment.
- [ ] `docker compose config` succeeds with a non-secret test `.env`.
- [ ] The stack builds and the manual smoke checklist passes.
- [ ] CodeQL, Dependabot, and secret-scanning show zero unresolved alerts, or every exception is documented.
- [ ] Release notes contain no private hosts, paths, accounts, recipe data, tokens, or infrastructure details.
- [ ] The target commit is recorded and reviewed before tagging.
- [ ] After explicit publication approval, a final protected pull request replaces `Unreleased` with the actual date and updates the README's unpublished-release wording.

## Publish Commands

Run these only after explicit approval to publish, after the finalization pull request is merged, and after replacing `<release-commit>` with that reviewed commit from `main`:

```bash
git fetch origin main --tags
git switch --detach <release-commit>
git tag -a v1.0.0 -m "Recipe Clipper v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 \
  --repo ckoenig673/recipe-clipper \
  --verify-tag \
  --title "Recipe Clipper v1.0.0" \
  --notes-file docs/releases/v1.0.0.md
```

The initial release publishes GitHub's source archives only. It does not publish prebuilt container images or an Android APK.

## Post-Publish Checks

- [ ] The tag and release resolve to the reviewed commit.
- [ ] Source archives are downloadable from the release page.
- [ ] The tagged README does not describe `v1.0.0` as unpublished.
- [ ] The tagged changelog records the actual publication date.
- [ ] A clean checkout of `v1.0.0` passes the documented Compose and smoke checks.
