"""Run a frozen 25–50 business frame in isolation; GET/DNS only, never CRM writes."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import mm_email as e
from mm_email_network import Crawler,DNSChecks,atomic_json
from email_baseline_capture import get_public

def collect(sample_path,output):
    sample=json.loads(Path(sample_path).read_text());cases=sample['cases']
    if not 25<=len(cases)<=50:raise ValueError('Frozen frame must contain 25–50 business units')
    root=Path(__file__).resolve().parents[1]
    for rel,digest in sample['engine_hashes'].items():
        if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Engine changed after frame freeze')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'cases').mkdir(exist_ok=True)
    lock=(out/'.collector.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise ValueError('VALIDATION_ALREADY_RUNNING')
    robots={};robots_log=[];dns=DNSChecks(out/'dns.json');summaries=[]
    def fetch(url):
        p=urlsplit(url);origin=p.scheme+'://'+p.netloc
        if origin not in robots:
            try:
                meta,body=get_public(origin+'/robots.txt')
                parser=RobotFileParser();parser.parse(body.decode('utf-8','replace').splitlines());robots[origin]=parser
                dest=out/('robots-'+meta['sha256']+'.txt');dest.write_bytes(body)
                robots_log.append({'origin':origin,'status':'captured','sha256':meta['sha256'],'path':dest.name})
            except ValueError as err:
                if str(err) in ('HTTP_404','HTTP_410'):robots[origin]=None;robots_log.append({'origin':origin,'status':str(err)})
                else:robots[origin]=False;robots_log.append({'origin':origin,'status':str(err)})
            except OSError as err:robots[origin]=False;robots_log.append({'origin':origin,'status':type(err).__name__})
            atomic_json(out/'robots-index.json',robots_log)
        if robots[origin] is False or (robots[origin] and not robots[origin].can_fetch('MoneyMachine-EvidenceReview',url)):
            raise ValueError('ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE')
        return get_public(url)
    for b in cases:
        start=time.monotonic();path=out/'cases'/(b['id']+'.json')
        if path.exists():
            doc=json.loads(path.read_text())
            if doc['business']!=b:raise ValueError('Existing case does not match frozen frame')
        else:
            pages,errors=Crawler(out,max_pages=3,max_requests=5,fetcher=fetch).crawl(b['public_website'])
            candidates={o['email'].rsplit('@',1)[-1] for p in pages for o in p['observations'] if o.get('email') and not o['syntax_error']}
            dns_results={domain:dns.check(domain) for domain in sorted(candidates)}
            at=dt.datetime.now(dt.timezone.utc)
            result=e.evaluate(b,pages,dns_results,at=at)
            metadata=[{k:p[k] for k in ('url','requested_url','captured_at','sha256','path','content_type','redirects') if k in p} for p in pages]
            doc={'business':b,'evaluated_at':at.isoformat(),'pages':metadata,'dns':dns_results,'result':result,'errors':errors,
                 'elapsed_seconds':round(time.monotonic()-start,2),'model_calls':0,'paid_ai_cost':0,'outbound_sent':0,
                 'outreach_eligible':False,'human_review_required':True,'independent_human_review':'NOT_PERFORMED'}
            atomic_json(path,doc)
        summary={'id':b['id'],'name':b['name'],'pages':len(doc['pages']),'identity':doc['result']['identity']['status'],
                 'selected':(doc['result']['selected'] or {}).get('email'),'errors':len(doc['errors'])}
        summaries.append(summary);print(json.dumps(summary),flush=True)
        atomic_json(out/'progress.json',summaries)
    metrics={'businesses':len(cases),'selected':sum(bool(s['selected']) for s in summaries),'NO_VERIFIED_EMAIL':sum(not s['selected'] for s in summaries),
       'unresolved_identities':sum(s['identity']!='HIGH' for s in summaries),'independent_human_reviews':0,
       'outreach_eligible_precision':None,'outreach_eligible_count':0,'precision_release':'BLOCKED_INDEPENDENT_REVIEW',
       'selection_precision_agent_review':None,'model_calls':0,'paid_ai_cost':0,'outbound_sent':0}
    atomic_json(out/'metrics.json',metrics);return metrics

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(collect(a.sample,a.output)),flush=True)
if __name__=='__main__':main()
