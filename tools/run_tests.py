"""Run each test module in its own process to isolate Tk state."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    modules = sorted((root / "tests").glob("test_*.py"))
    if sys.platform == "win32":
        modules = [path for path in modules if path.stem != "test_npu_top"]
    failed = []
    for path in modules:
        print(f"Testing {path.stem}", flush=True)
        with tempfile.TemporaryDirectory(prefix="serverlook-test-settings-") as settings:
            environment = dict(os.environ, APPDATA=settings)
            result = subprocess.run([sys.executable, "-m", "unittest", f"tests.{path.stem}"],
                                    cwd=root, env=environment, timeout=120)
        if result.returncode:
            failed.append(path.stem)
    print(f"{len(modules)} modules; failures: {', '.join(failed) or 'none'}")
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
