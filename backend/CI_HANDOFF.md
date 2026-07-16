# Backend CI Handoff

Repository-level backend checks are implemented in `.github/workflows/backend-ci.yml` and run for every pull request, every push to `main`, and manual dispatches.

- `backend-python311` installs the development dependencies on Python 3.11, runs the backend and shared-contract tests, upgrades an empty SQLite database, and rejects ORM/migration drift.
- `backend-container` builds the production image, starts it without secrets, waits for startup migrations and `/health`, and always removes the temporary container.

Both jobs require only read access to repository contents. They do not require GitHub secrets, external services, real sensor data, or a persistent database.

After both jobs have completed once on GitHub, a repository administrator should make `contract-docs`, `backend-python311`, and `backend-container` required checks for `main` in the repository ruleset or branch-protection settings.
