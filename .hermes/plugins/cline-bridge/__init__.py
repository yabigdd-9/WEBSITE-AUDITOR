"""Hermes -> Cline bridge for WEBSITE-AUDITOR.

The bridge deliberately permits only local providers by default and runs Cline
inside the configured repository. It returns machine-readable JSON to Hermes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

LOCAL_PROVIDERS = {"ollama", "lmstudio"}

CLINE_SYSTEM = """You are the coding worker for the WEBSITE-AUDITOR repository.
Work only inside the supplied repository.
Never send email/outreach, make purchases, deploy, push to remotes, rotate or print
secrets, or change external accounts/services. Do not run destructive git commands.
Prefer minimal diffs, preserve existing behaviour, run relevant local tests, and
finish with a concise summary of files changed, tests run, and remaining risks.
"""


def _json(data):
    return json.dumps(data, ensure_ascii=False)


def _run(cmd, cwd: Path, timeout: int, env=None):
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return {
            "returncode": cp.returncode,
            "stdout": cp.stdout[-30000:],
            "stderr": cp.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout": (exc.stdout or "")[-30000:] if isinstance(exc.stdout, str) else "",
            "stderr": "Cline task timed out.",
        }
    except Exception as exc:
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}


def register(ctx):
    def config():
        raw = ctx.get_config() or {}
        return {
            "repo_path": raw.get("repo_path", "/Users/dd/WEBSITE-AUDITOR"),
            "provider": raw.get("provider", "ollama"),
            "model": raw.get("model", "qwen3:4b"),
            "timeout_seconds": int(raw.get("timeout_seconds", 900)),
        }

    status_schema = {
        "name": "cline_status",
        "description": "Check whether Cline, git, the WEBSITE-AUDITOR repo, and the local provider configuration are ready.",
        "parameters": {"type": "object", "properties": {}},
    }

    delegate_schema = {
        "name": "cline_delegate",
        "description": (
            "Delegate a coding task in WEBSITE-AUDITOR to the local Cline CLI. "
            "Use mode=plan for analysis/review with no intended edits. Use mode=act only "
            "when the user explicitly asked to implement or modify repository files. "
            "The bridge is restricted to local zero-cost providers and blocks common "
            "push/send/destructive shell commands."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Specific coding/review/testing task for Cline.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["plan", "act"],
                    "default": "plan",
                    "description": "plan = inspect/propose; act = edit/test locally.",
                },
                "thinking": {
                    "type": "string",
                    "enum": ["none", "low", "medium", "high"],
                    "default": "medium",
                },
            },
            "required": ["task"],
        },
    }

    def handle_status(params, **kwargs):
        del params, kwargs
        cfg = config()
        repo = Path(cfg["repo_path"]).expanduser().resolve()
        cline = shutil.which("cline")
        hermes = shutil.which("hermes")
        git = shutil.which("git")

        result = {
            "success": bool(cline and git and repo.is_dir() and (repo / ".git").exists()),
            "repo": str(repo),
            "repo_exists": repo.is_dir(),
            "git_repo": (repo / ".git").exists(),
            "cline": cline,
            "hermes": hermes,
            "git": git,
            "provider": cfg["provider"],
            "model": cfg["model"],
            "provider_allowed": cfg["provider"] in LOCAL_PROVIDERS,
        }

        if cline:
            result["cline_version"] = _run([cline, "--version"], repo if repo.exists() else Path.home(), 30)
        if git and repo.exists():
            result["git_status"] = _run([git, "status", "--short", "--branch"], repo, 30)
        return _json(result)

    def handle_delegate(params, **kwargs):
        del kwargs
        cfg = config()
        repo = Path(cfg["repo_path"]).expanduser().resolve()
        provider = str(cfg["provider"]).strip()
        model = str(cfg["model"]).strip()
        timeout = max(30, min(int(cfg["timeout_seconds"]), 3600))
        mode = params.get("mode", "plan")
        thinking = params.get("thinking", "medium")
        task = str(params.get("task", "")).strip()

        if not task:
            return _json({"success": False, "error": "task is required"})
        if provider not in LOCAL_PROVIDERS:
            return _json({
                "success": False,
                "error": f"Provider '{provider}' blocked: cline-bridge is local/free-only.",
                "allowed_providers": sorted(LOCAL_PROVIDERS),
            })
        if not repo.is_dir() or not (repo / ".git").exists():
            return _json({"success": False, "error": f"Not a git repository: {repo}"})

        cline = shutil.which("cline")
        git = shutil.which("git")
        if not cline:
            return _json({"success": False, "error": "cline executable not found in PATH"})
        if not git:
            return _json({"success": False, "error": "git executable not found in PATH"})

        before = _run([git, "status", "--short"], repo, 30)

        env = os.environ.copy()
        env["CLINE_COMMAND_PERMISSIONS"] = json.dumps({
            "allow": [
                "git status*",
                "git diff*",
                "git log*",
                "git branch*",
                "python *",
                "python3 *",
                "pytest *",
                "npm test*",
                "npm run test*",
                "npm run lint*",
                "npm run build*",
            ],
            "deny": [
                "git push*",
                "git reset --hard*",
                "git clean*",
                "rm *",
                "sudo *",
                "curl *",
                "wget *",
                "ssh *",
                "scp *",
                "mail *",
                "sendmail *",
                "osascript *",
            ],
            "allowRedirects": False,
        })

        prompt = (
            task
            + "\n\nReturn a final concise report with: files inspected/changed, tests run, "
              "test results, and any blockers. Do not push or send anything."
        )

        cmd = [
            cline,
            "--json",
            "--cwd", str(repo),
            "--provider", provider,
            "--model", model,
            "--thinking", thinking,
            "--timeout", str(timeout),
            "--system", CLINE_SYSTEM,
        ]

        if mode == "plan":
            cmd += ["--plan", "--auto-approve", "true"]
        else:
            cmd += ["--auto-approve", "true"]

        cmd.append(prompt)
        run = _run(cmd, repo, timeout + 15, env=env)
        after = _run([git, "status", "--short"], repo, 30)
        diff = _run([git, "diff", "--stat"], repo, 30)

        return _json({
            "success": run["returncode"] == 0,
            "mode": mode,
            "provider": provider,
            "model": model,
            "repo": str(repo),
            "cline": run,
            "git_status_before": before,
            "git_status_after": after,
            "git_diff_stat": diff,
        })

    ctx.register_tool(
        name="cline_status",
        toolset="cline_bridge",
        schema=status_schema,
        handler=handle_status,
    )
    ctx.register_tool(
        name="cline_delegate",
        toolset="cline_bridge",
        schema=delegate_schema,
        handler=handle_delegate,
    )
