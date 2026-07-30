# Code Quality Assessment

## Test Coverage

- **Overall**: **None** (0%)
- **Unit Tests**: None — no test files, no framework, no fixtures
- **Integration Tests**: None
- **CI/CD**: None

There is nothing to regression-test the port against. Behavioural equivalence with the notebook will have to be established by characterising the existing logic (particularly contig-mode inference and Hydra flag assembly) with new tests written as part of the port.

## Code Quality Indicators

| Indicator | Status | Notes |
|---|---|---|
| **Linting** | Not configured | No ruff/flake8/pylint config |
| **Formatting** | Not configured | 2-space indentation throughout — non-PEP-8, consistent with Colab convention |
| **Type hints** | Absent | Zero annotations |
| **Docstrings** | Absent on all functions | The only prose is the module docstring and the closing instructions block |
| **Code style** | Internally consistent | Consistent 2-space indent, consistent naming |
| **User documentation** | **Good** | The closing instructions block (lines 568–596) is genuinely useful and covers all four design protocols with worked examples |
| **Error handling** | Poor | One bare `except:`; no validation of any user input; no error surfacing beyond a progress-bar colour change |
| **Logging** | Print statements only | `print("mode:", ...)`, `print(cmd)` |
| **Secrets management** | N/A | No credentials involved |

## Technical Debt

### Blocking for the port

| ID | Issue | Location |
|---|---|---|
| TD-1 | **File is not executable Python.** Cells 1, 2, 4 are commented out by Colab's exporter; the live code references undefined globals (`num_designs` at line 460, `path`/`contigs` throughout, `py3Dmol` imported only in Cell 5). | lines 21–354, 356–407, 478–517 |
| TD-2 | **Colab-only dependency** `google.colab.files` for upload and download. | lines 71, 87, 566 |
| TD-3 | **Root-requiring provisioning** (`apt-get install aria2`). | line 27 |
| TD-4 | **Provisioning embedded in application code** — 35 lines of `os.system` installs. | lines 26–65 |
| TD-5 | **Cross-cell global state** (`path`, `contigs`, `copies`, `num_designs`) with no explicit carrier. | Cells 2→3→4→5→6 |
| TD-6 | **`dist-packages` symlink** assumes Colab's filesystem layout. | line 55 |

### Correctness and safety

| ID | Issue | Location |
|---|---|---|
| TD-7 | **Shell injection surface.** Every user parameter is interpolated into a shell command string. The only mitigation is stripping `'` and `"` (lines 403–405), which neither prevents injection via `;`, `&&`, `$( )`, or backticks, nor preserves legitimate input. On a shared HPC cluster this is materially more serious than in a single-tenant Colab VM. | lines 234–343, 403–405, 504–517 |
| TD-8 | **Bare `except:`** swallows all exceptions including `KeyboardInterrupt` and `SystemExit`; a genuine AnAnaS failure is indistinguishable from "no symmetry found". | line 141 |
| TD-9 | **Parameter shadowing**: the loop variable `pdb` (line 350) overwrites the `pdb` function parameter of `run_diffusion`. Harmless today only because the parameter is not read after that point. | line 350 |
| TD-10 | **`plot_pdb` defined twice** with incompatible signatures; Cell 5's definition silently shadows Cell 3's, so re-running Cell 3's dropdown after Cell 5 renders the wrong thing. | lines 419, 521 |
| TD-11 | **Unvalidated coercion** `int(partial_T)` on a raw user string raises an unhandled `ValueError`. | line 304 |
| TD-12 | **No input validation anywhere** — contigs, hotspots, chains, PDB codes are all passed through unchecked. | throughout |
| TD-13 | **Fixed `/dev/shm/{n}.pdb` and `/dev/shm/pid` paths** collide between concurrent runs on a multi-user machine. | lines 147, 167, 180 |
| TD-14 | **Busy-wait polling at 10 Hz** (`time.sleep(0.1)`) burns CPU for the duration of every run. | lines 179, 220 |
| TD-15 | **Write-completeness heuristic** — treating a trailing `TER` as "file fully written" is a race that happens to work with tmpfs and RFdiffusion's write pattern. | line 182 |
| TD-16 | **`os.system` everywhere** instead of `subprocess` — no exit codes checked, no stderr captured, no timeouts. | throughout |
| TD-17 | **Silent fallbacks**: unrecognised `symmetry` values become `None` without warning; AnAnaS failure prints an error but continues with symmetry disabled. | lines 246–248, 277–289 |
| TD-18 | **Unbounded blocking loop** waiting for `params/done.txt` with no timeout. | lines 498–501 |

### Reproducibility

| ID | Issue |
|---|---|
| TD-19 | **No dependency manifest or lockfile.** Only `e3nn==0.5.5` is pinned; everything else — including two git installs — floats. |
| TD-20 | **`--no-dependencies` installs** leave transitive requirements unresolved and implicitly delegated to the ambient image. |
| TD-21 | **torch/CUDA/JAX never declared**, only inherited. The intended versions must be inferred from a wheel-index URL. |

## Patterns and Anti-patterns

### Good Patterns

- **Mode inference from contig syntax** (lines 250–268) — a genuinely elegant piece of domain logic that spares the user an explicit protocol choice. Worth preserving exactly, and worth being the first thing covered by tests in the port.
- **Filesystem-as-IPC progress streaming** — a pragmatic way to get live progress out of an opaque third-party script without forking it.
- **Collision-avoiding output paths** (lines 385–387) — appends a random suffix when the target name is taken.
- **Background weight download overlapped with code install** (lines 30–37) — meaningfully reduces cold-start latency.
- **Post-run PDB repair** (`fix_pdb`, lines 345–352) — ensures output numbering matches the requested contigs, which downstream tools depend on.
- **Excellent user-facing documentation** — the instructions block explains all four protocols with concrete, copy-pasteable examples.

### Anti-patterns

- Provisioning inside application code (TD-4)
- Shell command construction by string concatenation with user input (TD-7)
- Bare `except:` (TD-8)
- Global-namespace state passing between execution units (TD-5)
- `os.system` in place of `subprocess` (TD-16)
- Duplicate function definitions in one file (TD-10)
- Magic string dispatch without validation (TD-17)
- Hard-coded absolute paths (`/dev/shm`, `./ananas`, `/usr/local/lib/python3.*/dist-packages`)
- No separation of concerns — provisioning, domain logic, process management, presentation, and export all interleaved in one file

## Overall Assessment

Judged as a Colab notebook, this is **good work**: it is well-documented for its users, the domain logic is thoughtful, and the progress-streaming trick is clever. Nearly every issue listed above is a reasonable trade-off in a single-tenant, ephemeral, root-enabled VM where the user is also the operator.

Judged as the starting point for a **multi-user web application on a shared HPC cluster**, the same properties become liabilities. The three that must be addressed rather than merely carried over:

1. **Shell injection (TD-7)** — acceptable when you can only attack yourself; not acceptable when a web form reaches a shared login/compute node.
2. **Fixed `/dev/shm` paths (TD-13)** — silently correct on Colab, silently *wrong* with concurrent users.
3. **No dependency manifest (TD-19/20/21)** — the entire premise of the requested `uv` migration, and the work with the least ambiguity and the most immediate payoff.

The good news for scoping: roughly **120 lines** of `run_diffusion` plus the mode-inference block constitute the real intellectual content. Everything else is provisioning (to be replaced by `uv` + Slurm), presentation (to be replaced by a web UI), or Colab glue (to be deleted).
