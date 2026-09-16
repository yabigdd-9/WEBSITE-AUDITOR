"""Bounded capability check for the installed Hermes; model execution stays held.

Only CLI help/version are invoked. Installing a provider is not this adapter's
job, and a free-model label alone cannot authorize inference or tools.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def redact(text):
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]+)\b', '[REDACTED]', text)


def result(status, summary, evidence=(), risks=(), next_action='Review the blocker'):
    return dict(status=status, summary=summary, evidence=list(evidence), risks=list(risks),
                next_action=next_action, model_calls=0, paid_ai_cost=0, external_actions=0)


def inspect(executable='hermes'):
    binary=shutil.which(executable)
    if not binary or Path(binary).stat().st_size == 0:
        return result('BLOCKED_MISSING', 'Hermes executable missing or empty')
    evidence=[]
    for args in ([binary,'--help'], [binary,'--version'], [binary,'chat','--help']):
        try:
            r=subprocess.run(args,capture_output=True,text=True,timeout=30)
        except (OSError,subprocess.TimeoutExpired) as e:
            return result('FAILED',type(e).__name__,evidence)
        evidence.append({'command':args,'exit_code':r.returncode,'stdout':redact(r.stdout),'stderr':redact(r.stderr)})
        if r.returncode:
            return result('FAILED','Hermes capability command failed',evidence)
    helptext=evidence[-1]['stdout']
    if not all(flag in helptext for flag in ('--query-file','--oneshot','--provider','--safe-mode')):
        return result('BLOCKED_INTERFACE','Required bounded chat interface unavailable',evidence)
    doc=result('PASS','Installed Hermes supports bounded chat queries',evidence,
               ['Capability detection does not prove successful model execution'],
               'Verify a zero-cost isolated provider before any inference')
    doc['supported_query_interface']=['chat','--query-file','PATH','--oneshot','--safe-mode']
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hermes',default='hermes')
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--probe',action='store_true')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv);doc=inspect(a.hermes)
    if a.smoke and doc['status']=='PASS':
        # Fail closed even if inherited provider credentials or :free names exist.
        doc.update(status='BLOCKED_COST',summary='No certified zero-cost isolated inference route is enabled',
                   next_action='Configure and independently certify a local provider, then implement its bounded runner')
        doc['smoke_payload']='HERMES_CONTROL_PLANE_OK'
        doc['smoke_executed']=False
    raw=json.dumps(doc,indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(raw+'\n')
    print(raw)
    return 0 if doc['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
