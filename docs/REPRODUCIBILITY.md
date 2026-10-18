# Reproducing the reviewed environment

`constraints/windows-py314.txt` pins the resolved runtime dependencies, their transitive dependencies, pytest, and build tools for **CPython 3.14.7 on Windows x64**. `pyproject.toml` retains compatible dependency ranges for library consumers. A normal unconstrained `pip install .` does not reproduce this baseline.

From a repository checkout in PowerShell:

```powershell
py -3.14 -m venv .venv
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install --constraint constraints/windows-py314.txt pip
& $python -m pip install --constraint constraints/windows-py314.txt build setuptools wheel
& $python -m pip install --constraint constraints/windows-py314.txt --no-build-isolation -e '.[dev]'
& $python -m pytest -q
& $python -m pip check
& $python -m build --wheel --no-isolation
```

`--no-isolation` / `--no-build-isolation` ensure the build uses the explicitly installed, pinned tools. Without these flags, a separate build environment can resolve different versions of setuptools.

To verify the wheel outside the checkout, create another venv, use its Python, and install the wheel with an absolute path to the constraints file:

```powershell
& $wheelPython -m pip install --constraint $constraintsPath $wheelPath
& $wheelPython -m pip check
& $wheelCli discover-sources --goal transformer
```

`$wheelPython`, `$wheelCli`, `$constraintsPath`, and `$wheelPath` refer to that venv's Python/CLI and the absolute constraint/wheel paths. Run the CLI from a temporary directory so an import from the source checkout cannot hide a packaging omission.

These are version constraints, not an artifact hash lock: package availability still depends on the configured index, and wheels are not claimed to be byte-identical. Other Python versions or operating systems require their own resolved baseline and test run. No cross-platform installation claim follows from the package's declared Python minimum.

When updating dependencies, resolve in a fresh venv, update the pins including transitive dependencies, run the complete tests and MCP SDK stdio round trip, then build and install the wheel in a separate venv. Record the actual Python version, installed packages, and results before replacing this baseline.
