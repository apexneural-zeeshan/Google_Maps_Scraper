# Git Rules

## Branching

- `main` — always deployable, protected.
- `feat/<short-name>` — new features.
- `fix/<short-name>` — bug fixes.
- `chore/<short-name>` — maintenance, config, dependencies.
- `docs/<short-name>` — documentation changes.

## Commit Messages

Follow Conventional Commits:

```
<type>: <short description>

[optional body explaining why]
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`, `perf`.

Examples:
- `feat: add SerpAPI search integration`
- `fix: handle empty grid when radius < 0.1km`
- `chore: update fastapi to 0.111.0`

## PR Workflow

1. Branch from `main`.
2. Keep PRs focused — one feature or fix per PR.
3. Write descriptive PR titles matching the commit convention.
4. Include a test plan in the PR description.
5. Squash-merge to `main`.
6. Delete branch after merge.
