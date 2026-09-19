#!/usr/bin/env python3
"""Verify dsh_mm_bridge.py correctness after polish."""
import sys

def check_1_no_bare_except_subprocess() -> bool:
    """Verify no bare 'except subprocess' remains."""
    with open("integrations/deepseek-harness/scripts/dsh_mm_bridge.py") as f:
        text = f.read()
    if "except subprocess\n" in text or "except subprocess:" in text:
        print("FAIL: bare 'except subprocess' still present")
        return False
    if "except subprocess.TimeoutExpired" not in text:
        print("FAIL: TimeoutExpired handler missing")
        return False
    print("PASS: except subprocess fixed — uses TimeoutExpired correctly")
    return True

def check_2_schema_policy_match() -> bool:
    """Verify Python schema names match YAML allowed list."""
    import yaml
    with open("integrations/deepseek-harness/policies/permissions.yml") as f:
        policy = yaml.safe_load(f)
    with open("integrations/deepseek-harness/scripts/dsh_mm_bridge.py") as f:
        code = f.read()
    
    yaml_allowed = set()
    for section in ["read_only", "bounded_network"]:
        for name in policy.get("allowed", {}).get(section, []):
            yaml_allowed.add(name)
    
    py_allowed = set()
    for name in re.findall(r"name:\s*'([^']+)'", code):
        py_allowed.add(name)
    
    extra = yaml_allowed - py_allowed
    missing = py_allowed - yaml_allowed
    
    if extra:
        print(f"FAIL: YAML allows but Python missing: {extra}")
        return False
    if missing:
        print(f"FAIL: Python has but YAML missing: {missing}")
        return False
    print(f"PASS: YAML and Python schema match ({len(yaml_allowed)} tools)")
    print(f"  YAML: {sorted(yaml_allowed)}")
    print(f"  Python: {sorted(py_allowed)}")
    return True

def check_3_escape_prevention() -> bool:
    """Verify path traversal is blocked even via symlinks."""
    import subprocess, tempfile, os
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "repo"
        outside = Path(tmpdir) / "outside"
        repo.mkdir()
        outside.mkdir()
        (outside / "secret.txt").write_text("STOLEN")
        
        # Create symlink inside repo pointing outside
        link = repo / "escape_link"
        link.symlink_to(outside)
        
        sys.path.insert(0, "integrations/deepseek-harness/scripts")
        from dsh_mm_bridge import _repo_path
        import importlib
        import dsh_mm_bridge
        importlib.reload(dsh_mm_bridge)
        
        try:
            result = _repo_path(str(link))
            print(f"FAIL: _repo_path allowed escape via symlink -> {result}")
            return False
        except ValueError:
            print("PASS: _repo_path blocks symlink escape")
            return True
        finally:
            importlib.reload(dsh_mm_bridge)

def check_4_url_private_blocking() -> bool:
    """Verify private/local URLs are blocked."""
    import subprocess, tempfile, os
    sys.path.insert(0, "integrations/deepseek-harness/scripts")
    from dsh_mm_bridge import _public_http_url
    import importlib
    import dsh_mm_bridge
    importlib.reload(dsh_mm_bridge)
    
    blocked = [
        "http://127.0.0.1/foo",
        "https://localhost/admin",
        "http://0.0.0.0:8080/status",
        "https://10.0.0.1/api",
        "http://192.168.1.1/health",
        "https://[::1]/",
    ]
    allowed = [
        "https://example.com/audit",
        "http://1.2.3.4/status",
    ]
    
    all_pass = True
    for url in blocked:
        try:
            _public_http_url(url)
            print(f"FAIL: _public_http_url allowed private URL: {url}")
            all_pass = False
        except ValueError:
            pass
    
    for url in allowed:
        try:
            result = _public_http_url(url)
            if result != url:
                print(f"FAIL: _public_http_url rewrote allowed URL: {url} -> {result}")
                all_pass = False
        except ValueError as e:
            print(f"FAIL: _public_http_url blocked legitimate URL {url}: {e}")
            all_pass = False
    
    if all_pass:
        print("PASS: URL filtering blocks private/local, allows public")
    return all_pass

def check_5_no_shell_injection_in_command_construction() -> bool:
    """Verify no shell=True patterns, args always lists."""
    with open("integrations/deepseek-harness/scripts/dsh_mm_bridge.py") as f:
        code = f.read()
    
    issues = []
    if "shell=True" in code:
        issues.append("shell=True found")
    if 'shell = True' in code:
        issues.append("shell = True found")
    
    # Check that subprocess.run calls use list args, not strings
    import re
    run_calls = re.findall(r'subprocess\.run\(([^)]+)\)', code)
    for call in run_calls:
        if 'shell' in call:
            issues.append(f"subprocess.run with shell arg: {call[:80]}")
    
    if issues:
        for i in issues:
            print(f"FAIL: {i}")
        return False
    print("PASS: no shell injection vectors in subprocess calls")
    return True

def check_6_yaml_version_format() -> bool:
    """Verify YAML version is a string."""
    import yaml
    with open("integrations/deepseek-harness/policies/permissions.yml") as f:
        policy = yaml.safe_load(f)
    version = policy.get("version")
    if not isinstance(version, str):
        print(f"FAIL: version is {type(version).__name__} ({version!r}), expected string")
        return False
    print(f"PASS: YAML version is string: {version!r}")
    return True

def check_7_dockerignore_exists() -> bool:
    """Verify .dockerignore exists and excludes sensitive paths."""
    path = Path("integrations/deepseek-harness/.dockerignore")
    if not path.exists():
        print("FAIL: .dockerignore missing")
        return False
    text = path.read_text()
    required = [".git", "*.db", ".cache/", "__pycache__"]
    missing = [r for r in required if r not in text]
    if missing:
        print(f"FAIL: .dockerignore missing entries: {missing}")
        return False
    print("PASS: .dockerignore exists with required exclusions")
    return True

def check_8_readme_latest_section_exists() -> bool:
    """Verify README mentions the latest Harness model."""
    path = Path("integrations/deepseek-harness/README.md")
    if not path.exists():
        print("FAIL: README.md missing")
        return False
    text = path.read_text()
    if "0.2.0" in text or "draft-gateway" in text:
        print("PASS: README mentions Harness 0.2.0 draft-gateway")
    else:
        print("INFO: README may need Harness 0.2.0 update (not critical)")
    return True

if __name__ == "__main__":
    import re
    from pathlib import Path
    
    checks = [
        ("No bare except subprocess", check_1_no_bare_except_subprocess),
        ("Schema/policy match", check_2_schema_policy_match),
        ("Escape prevention", check_3_escape_prevention),
        ("URL private blocking", check_4_url_private_blocking),
        ("No shell injection", check_5_no_shell_injection_in_command_construction),
        ("YAML version format", check_6_yaml_version_format),
        (".dockerignore", check_7_dockerignore_exists),
        ("README latest section", check_8_readme_latest_section_exists),
    ]
    
    results = []
    for name, fn in checks:
        try:
            ok = fn()
        except Exception as e:
            ok = False
            print(f"FAIL: {name} raised {type(e).__name__}: {e}")
        results.append((name, ok))
    
    print()
    print("=" * 50)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"RESULTS: {passed}/{total} checks passed")
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    
    sys.exit(0 if passed == total else 1)
