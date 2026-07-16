# AI Agent Instructions

## Required reading

Before changing code, read:

1. `docs/module-specs/00_SHARED_CONTRACT.md`
2. The target module specification in `docs/module-specs/`
3. The target directory README
4. `CONTRIBUTING.md`

## Scope rules

- Work only inside the assigned module plus shared contracts/fixtures required by that module.
- Do not change public fields, enums, endpoint paths, or privacy rules without updating the shared contract and affected tests.
- Inspect existing code before implementing. Preserve unrelated user changes.
- Prefer small, testable components and deterministic behavior.
- Never commit secrets, raw audio, RGB images, personal identifiers, or large captured datasets.

## Completion rules

- Implement the requested behavior; do not stop at a plan or pseudocode.
- Add or update tests and run the relevant test suite.
- Update the module README and handoff document.
- Report changed files, commands run, test results, limitations, and any cross-module action required.

## Module boundaries

- Module 1: `edge/hardware/`
- Module 2: `edge/ml/`
- Module 3: `backend/`, excluding the recommendation algorithm owned by Module 4
- Module 4: `frontend/` and the recommendation adapter package integrated into `backend/`
- Shared interfaces: `shared/contracts/`, `shared/fixtures/`, and `docs/module-specs/00_SHARED_CONTRACT.md`
