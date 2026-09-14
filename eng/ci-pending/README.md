# Pending GitHub Actions workflows (P1/P5)

These YAML files belong in `.github/workflows/`.

The implementing OAuth token lacked the `workflow` scope, so they cannot be
pushed under `.github/workflows/` from this agent. A maintainer with
`workflow` scope (or the GitHub web UI) should move them:

```bash
mkdir -p .github/workflows
cp eng/ci-pending/*.yml .github/workflows/
git add .github/workflows
git commit -m "P1/P5: activate OpenAPI CI workflows (Badge OFF)"
git push
```

Then delete this `eng/ci-pending/` directory in a follow-up tip.
Stevie Blind Review on the activated workflows.
