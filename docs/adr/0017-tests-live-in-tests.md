# ADR-0017: Tests live in `tests/`, and everything has a test

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

Two requirements, stated together on 2026-11-10:

1. **All tests are stored in `tests/`.**
2. **Everything has a test.**

Neither is controversial; both are the kind of rule that quietly stops being true.
The repository already demonstrates the problem. The release pipeline was the first
code in the tree, so its tests were written where the code was —
`tools/release/tests/` — following the common Python convention of co-locating
tests with the module they cover. That is defensible for one tool and wrong for
the second one:

- **Discovery becomes per-tool.** `unittest` finds tests by path, so every tool
  would add another `-s tools/<tool>/tests -t tools/<tool>` invocation to every
  contributor's command, every README, and every CI job. The set of tests is then
  something you reconstruct by reading CI, not something one command finds.
- **The convention has to be guessed.** With tests in both `tests/` and
  `tools/*/tests/`, a new contributor has to know which tool follows which rule.
- **"Everything has a test" has no meaning without a check.** As an aspiration it
  survives until the first deadline. Four modules in `tools/release/aios_release/`
  already had only *indirect* coverage — `canonical`, `signing`, `evidence`, and
  `demo` were each exercised through `test_manifest`, `test_promote` and
  `test_cli`, but none had a test module that would fail if its own behaviour
  broke. That is exactly the gap a written rule is supposed to prevent.

"Everything" also needs defining, because not every artefact is testable the same
way. A pure function has behaviour to assert. A shell script that calls `dnf` has
almost none without a machine. A workflow is validated by being parsed. A document
is validated by its links and its index.

## Decision

### 1. One test tree, mirroring the code

```
tests/
  __init__.py
  release/            tests for tools/release/aios_release/
    __init__.py
    factories.py      shared construction helpers, not tests
    test_manifest.py
    test_canonical.py
    …
  layout/             checks the rules in this ADR
  docs/               checks the documentation tree
```

A test module for `tools/<area>/<package>/<module>.py` is
`tests/<area>/test_<module>.py`. Subdirectories of `tests/` that hold no
production code (`layout`, `docs`) are named for the thing they check.

### 2. Nothing named `test_*` lives outside `tests/`

There is no second convention, not even for a tool that is tiny. `tools/` holds
code; `tests/` holds tests.

### 3. Every module has a test module

Every `.py` file under a Python package in `tools/` has a matching
`tests/<area>/test_<module>.py`, except `__init__.py` and `__main__.py`, which are
import wiring rather than behaviour.

This is enforced by `tests/layout/test_layout.py`, which walks the tree and fails
with the list of missing files. Adding a module without a test now fails the
suite, in the same way a failing assertion does.

### 4. Every change adds a test that fails without it

The rule for behaviour: a bug fix adds a test that reproduces the bug from the
state it was reported in; a feature adds a test that would fail if the feature
were removed. The two design bugs found in the release pipeline — soak measured
from a moving pointer, `supersedes` holding the previous digest — were caught
because the tests existed before the code was trusted, and both now carry the test
named after the failure.

This rule is not mechanically enforceable and is therefore a review obligation,
stated here so that "no test" is a visible exception rather than the default.

### 5. Coverage bar by artefact

| Artefact | Minimum bar | Enforced by |
|----------|-------------|-------------|
| Python module with behaviour | a `test_<module>.py` covering its public functions | `tests/layout` (presence only) |
| Python module that only re-exports | import test | the module's consumer tests |
| `ci/*.sh` | `bash -n` syntax check in CI | `tests.yml` |
| GitHub workflow | parsed, with the expected jobs present | `ci/validate-workflows.py` |
| Markdown | relative links resolve; every doc is indexed | `tests/docs` |

The shell row is the weak one and is stated as such: `bash -n` proves a script
parses, not that it works. `ci/promote.sh` has no behavioural test because
exercising it needs a registry, a signing key and a git remote. When one of those
becomes available in a test harness, this table changes; until then, the gap is
recorded rather than papered over.

### 6. One command runs the suite

```bash
PYTHONPATH=tools/release python -m unittest discover -s tests -t .
```

`tests.yml` runs exactly this on every push and pull request, then the static
checks from the table above. No test runner is installed: `unittest` is in the
standard library, and the suite runs on a machine with nothing but Python.

## Consequences

### Positive

- **One command finds every test**, and the same command works in CI, in a
  container, and on a fresh laptop. Adding a tool adds a directory, not a command.
- **Moving code does not move tests.** A module can be split, renamed or moved
  between packages without dragging files across the tree.
- **The rule is checked, not remembered.** The layout test turns a convention into
  a failing assertion, which is the only kind of documentation that stays true.
- **Coverage gaps became visible.** Writing this ADR found four modules with no
  direct test; they have them now.

### Negative / costs

- **Tests are far from the code.** A reader of `promote.py` no longer sees a
  neighbouring `tests/` directory. The layout test catches a *missing* test file;
  it does not catch a *stale* one left behind by a rename.
- **The command is longer.** `tests/` needs package markers and a `PYTHONPATH`, so
  the invocation is not plain `python -m unittest`. That is one documented line
  instead of zero.
- **The layout test proves presence, not quality.** An empty `test_foo.py`
  satisfies it. The rule this ADR can enforce is "a test module exists"; "the test
  is worth having" remains a review judgement.
- **A shared `tests/` tree is a merge hotspot** once several subsystems are under
  active development. Mirroring subdirectories keeps the blast radius to one
  directory per subsystem.

### Neutral / follow-on

- `factories.py` is shared construction code, not a test module, and deliberately
  does not start with `test_`. When a second subsystem needs factories, they move
  to `tests/<area>/factories.py` rather than becoming a repository-wide fixture
  library.
- The suite pins one Python version in CI. Stdlib-only code makes a version matrix
  cheap to add later if a compatibility question ever appears.

## Alternatives considered

**Keep tests next to the code (`tools/release/tests/`).** Rejected by the
requirement, and for the structural reason above: discovery would become one
command per tool. It was a reasonable default while there was exactly one tool.

**Use `pytest` with `testpaths = tests`.** Rejected for now. It would give
fixtures, parametrisation and better failure output, at the cost of a dependency
the project does not otherwise need. The layout chosen here is compatible with
switching later — `pytest` collects `unittest` cases and reads the same tree — so
this is a reversible decision rather than a commitment.

**Write the rule down and trust review.** Rejected. "Everything has a test" is
precisely the instruction that decays: each exception looks reasonable in
isolation, and the aggregate is visible only when someone counts. The layout test
counts.

**One `tests/test_all.py`.** Rejected. It gives one command and no structure, and
the file becomes a merge conflict proportional to the team.

**Enforce coverage percentage.** Rejected as premature. A percentage gate rewards
tests written to raise a number, and there is no meaningful target when half the
tree is documents and shell. Revisit when there is a package with runnable
behaviour, not before.

## Follow-ups

- Add behavioural tests for `ci/promote.sh` once a registry and signing key exist
  in a test harness.
- Decide whether the layout rule should extend to `ci/*.sh`, requiring a test for
  each script.
- Revisit coverage measurement when `aios-updated` and the shell exist.
- Add a `tests/` entry to the roadmap legend so new subsystems are expected to
  bring their tests with them.
