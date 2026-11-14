"""The bounded adapter imports from a foreign entry point without network I/O."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "money-machine/mm_email_network.py"
PROBE = r"""
import importlib.util,json,runpy,socket,sys
from pathlib import Path
root=Path(sys.argv[1]);adapter=Path(sys.argv[2]);kind=sys.argv[3]
sys.path.insert(0,str(root))
def forbidden(*args,**kwargs):
    raise AssertionError("Network forbidden in adapter import regression")
socket.socket.connect=forbidden
socket.getaddrinfo=forbidden
assert str(adapter.parent) not in sys.path
for attempt in range(2):
    if kind == "spec":
        spec=importlib.util.spec_from_file_location("isolated_email_adapter",adapter)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        namespace=vars(module)
    else:
        namespace=runpy.run_path(str(adapter),run_name="isolated_email_adapter")
    assert callable(namespace["Crawler"])
    assert callable(namespace["DNSChecks"])
assert sys.path.count(str(adapter.parent)) == 1
print(json.dumps({"imported":True,"sibling_path_entries":1,"network_calls":0}))
"""


@pytest.mark.parametrize("entry_point", ["spec", "runpy"])
def test_adapter_imports_idempotently_from_unrelated_directory(tmp_path, entry_point):
    environment = {key: value for key, value in os.environ.items()
                   if not any(word in key.upper() for word in
                              ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
    environment.update(MM_ROOT=str(tmp_path), MM_EXTERNAL_SEND_DISABLED="1")
    result = subprocess.run([sys.executable, "-I", "-B", "-c", PROBE,
                             str(ROOT), str(ADAPTER), entry_point], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "imported": True, "sibling_path_entries": 1, "network_calls": 0}
