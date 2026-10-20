import pathlib,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c',"import time,pathlib;time.sleep(1);pathlib.Path('/Users/dd/Documents/Codex/2026-10-19/x20-r/work/repo-completion/work/codex-r00/pytest-financial-verified-ops/test_module_timeout_kills_desc0/child-stopped').touch()"])
pathlib.Path('/Users/dd/Documents/Codex/2026-10-19/x20-r/work/repo-completion/work/codex-r00/pytest-financial-verified-ops/test_module_timeout_kills_desc0/child.pid').write_text(str(child.pid))
time.sleep(60)
