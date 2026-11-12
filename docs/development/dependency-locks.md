# Dependency and Container Pinning

Recipe Clipper separates human-edited dependency intent from reproducible locks:

- Each worker's `requirements.in` lists its direct Python dependencies.
- Each `requirements.txt` is the complete exact lock installed in that container.
- `backend/requirements-dev.txt` adds the exact backend test dependencies used by CI.
- `ocr-worker/requirements-torch.txt` separately locks the CPU-only PyTorch wheels
  installed from the PyTorch package index.
- Root `package-lock.json` remains the exact Node/Playwright lock used by `npm ci`.

Change an `.in` file first. Regenerate the corresponding `.txt` lock in a clean
Python 3.11 environment, review every transitive change, run the relevant tests,
and build the affected container before merging. Do not hand-edit a lock without
updating or confirming its source intent.

Every Dockerfile base image is pinned by a readable release tag and an immutable
multi-architecture digest. When updating one, verify that the tag and digest
refer to the same manifest, rebuild the affected service, and exercise its
health or smoke check. A digest refresh is an explicit maintenance change;
normal builds must not silently move to a newer base image.

Dependabot checks the npm, Python, Docker, and GitHub Actions ecosystems monthly.
Its pull requests are update proposals, not automatic permission to merge:
review regenerated locks and pass the same service-specific validation first.
