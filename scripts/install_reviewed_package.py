"""Build only this reviewed checkout, then hash-verify its local wheel offline.

Third-party build/runtime tools must already be installed from the committed
hash lock. No build isolation, dependency resolution or remote index is used.
"""

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="wa-owned-wheel-") as directory:
        subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", directory, str(root)],
            check=True,
        )
        wheels = list(Path(directory).glob("website_auditor-*.whl"))
        if len(wheels) != 1:
            raise ValueError("Expected one built wheel from the reviewed checkout")
        wheel = wheels[0]
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        requirement = Path(directory) / "owned-wheel.txt"
        requirement.write_text(f"{wheel.as_uri()} --hash=sha256:{digest}\n")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--require-hashes",
             "--no-deps", "--no-index", "-r", str(requirement)], check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
