"""Transparent local estimates; no calibrated conversion claims or AI calls."""
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from mm_core import now, sha, fresh, timestamp, UTC, eligible, evidence, artifact_valid, event

ONTOLOGY = ('acquisition','conversion','sales','quoting','lead_capture','booking','follow_up','crm','operations','admin','retention','reviews','referrals','automation','reporting','customer_experience')
OFFERS = {
 'lead_capture':('Lead Capture Rescue','One existing enquiry flow; retain current platform and inbox',4,8),
 'reviews':('Trust Conversion Upgrade','Use client-supplied authentic proof; remove unsupported claims',4,10),
 'conversion':('Mobile Conversion Upgrade','One verified mobile bottleneck with before/after QA',5,12),
 'quoting':('Smart Quote System','One quoting workflow with explicit estimate limits',8,20),
 'follow_up':('Lead Recovery System','Local follow-up queue; external actions require approval',8,16),
 'booking':('Booking Automation','One booking flow on approved existing tools',6,14),
 'customer_experience':('Digital Modernisation','One bounded customer journey after diagnosis',8,20),
 'operations':('Operations Automation','One measured administrative workflow',8,20),
}
WEIGHTS={'pain':.20,'evidence_confidence':.20,'freshness':.10,'fit':.10,'ability_to_pay':.05,'urgency':.05,'decision_access':.05,'demoability':.10,'ease':.05,'upsell':.05,'recurring':.05}

def bounded(value,lo,hi,name):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError(name+' outside valid range')
    return value

def interval(data,key,lo,hi):
    x=data[key]
    if not isinstance(x,list) or len(x)!=2:raise ValueError(key+' requires [low, high]')
    a,b=[bounded(v,lo,hi,key) for v in x]
    if a>b:raise ValueError(key+' range inverted')
    return a,b

def expected_value(data):
    r=interval(data,'p_reply',0,1);c=interval(data,'p_conversation_given_reply',0,1);w=interval(data,'p_win_given_conversation',0,1)
    deal=interval(data,'deal_nzd',0,1000000);margin=interval(data,'gross_margin',0,1);hours=interval(data,'human_hours',.01,10000)
    ev=[r[i]*c[i]*w[i]*deal[i]*margin[i] for i in (0,1)]
    return {'ev_nzd':[round(x,2) for x in ev],'ev_per_human_hour_nzd':[round(ev[0]/hours[1],2),round(ev[1]/hours[0],2)],'ev_per_ai_dollar':None,'ai_cost_nzd':0,'cost_ratio_note':'Undefined at zero AI cost; do not divide by zero or claim infinite ROI','basis':'Uncalibrated scenario assumptions, not measured conversion probabilities'}

def score(d,bid,eid,dimensions,assumptions):
    if set(dimensions)!=set(WEIGHTS):raise ValueError('All eleven dimensions required; do not silently fill unknowns')
    values={k:bounded(dimensions[k],0,100,k) for k in WEIGHTS}
    reasons=[]
    try:eligible(d,bid);e=evidence(d,eid,bid)
    except ValueError as ex:reasons.append(str(ex));e=None
    if e:
        # Evidence confidence and age are derived, not supplied as flattering scores.
        values['evidence_confidence']=min(values['evidence_confidence'],100*e['confidence'])
        age=(dt.datetime.now(UTC)-timestamp(e['checked_at'])).total_seconds()/86400
        values['freshness']=max(0,100*(1-age/7))
    else:values['evidence_confidence']=0;values['freshness']=0
    result=expected_value(assumptions)
    result.update({'score':round(sum(values[k]*WEIGHTS[k] for k in WEIGHTS),1) if not reasons else 0,'eligible_for_commercial_work':not reasons,'blockers':reasons,'dimensions':values,'weights':WEIGHTS,'evidence_id':eid,'calculated_at':now()})
    if reasons:result['ev_nzd']=[0,0];result['ev_per_human_hour_nzd']=[0,0]
    return result

def save_score(d,bid,eid,dimensions,assumptions):
    result=score(d,bid,eid,dimensions,assumptions)
    inputs=json.dumps({'dimensions':dimensions,'assumptions':assumptions},sort_keys=True)
    d.execute('INSERT INTO mm_scores VALUES(?,?,?,?,?) ON CONFLICT(business_id) DO UPDATE SET evidence_id=excluded.evidence_id,inputs_json=excluded.inputs_json,computed_json=excluded.computed_json,calculated_at=excluded.calculated_at',(bid,eid,inputs,json.dumps(result),now()));return result

def pricing(problem,hours=None,hourly_floor=65,complexity=1,support_hours=1,proof_strength=.5,urgency=0):
    if problem not in OFFERS:raise ValueError('No validated offer mapping for problem; scope locally first')
    name,scope,lo,hi=OFFERS[problem];hours=hours or [lo,hi]
    h1,h2=interval({'hours':list(hours)},'hours',.1,1000)
    bounded(hourly_floor,1,1000,'hourly floor');bounded(complexity,1,3,'complexity');bounded(support_hours,0,100,'support');bounded(proof_strength,0,1,'proof');bounded(urgency,0,1,'urgency')
    ceil25=lambda x:int(math.ceil(x/25)*25)
    floor=ceil25((h2+support_hours)*hourly_floor*complexity)
    recommend=ceil25(floor*(1.15+.15*proof_strength+.10*urgency))
    return {'offer':name,'scope':scope,'hours_range':[h1,h2],'floor_nzd':floor,'recommended_nzd':recommend,'premium_nzd':ceil25(recommend*1.35),'gst':'Unconfirmed; determine before issuing quote','note':'Cost-based scenarios; no evidence of willingness to pay. Delivery/access and scope must be confirmed.'}

def model_request(d,model,provider,purpose):
    # No execution implementation: paid, unknown and unavailable routes all fail closed.
    # Attempt committed independently by the CLI so failure cannot erase the audit row.
    permitted=model.endswith(':free') and provider in ('nous','openrouter')
    error='Model execution paused; no provider call made' if permitted else 'Route not permitted by zero-cost policy'
    run=sha(now()+purpose)
    d.execute('INSERT INTO mm_model_invocations(run_key,model,provider,purpose_hash,status,created_at,finished_at,error) VALUES(?,?,?,?,?,?,?,?)',(run,model,provider,sha(purpose),'blocked',now(),now(),error));return {'run_key':run,'status':'blocked','model_calls':0,'cost_usd':0,'reason':error}

def claim_job(d,key,kind,bid=None):
    t=dt.datetime.now(UTC)
    # caller's transaction must hold the write lock; claim update uses a predicate too.
    d.execute("INSERT OR IGNORE INTO mm_jobs(job_key,kind,business_id,state,updated_at) VALUES(?,?,?,'pending',?)",(key,kind,bid,now()))
    j=d.execute('SELECT * FROM mm_jobs WHERE job_key=?',(key,)).fetchone()
    if j['kind']!=kind or j['business_id']!=bid:raise ValueError('Job key already belongs to different work')
    if j['state']=='completed':return dict(j)
    if j['state']=='running' and j['lease_until'] and timestamp(j['lease_until'])>t:raise ValueError('Job already leased')
    if j['attempts']>=3:raise ValueError('Retry budget exhausted')
    d.execute("UPDATE mm_jobs SET state='running',attempts=attempts+1,lease_until=?,updated_at=?,error=NULL WHERE job_key=?",((t+dt.timedelta(minutes=5)).isoformat(),now(),key));return dict(d.execute('SELECT * FROM mm_jobs WHERE job_key=?',(key,)).fetchone())

def finish_job(d,key,checkpoint,error=None):
    j=d.execute('SELECT * FROM mm_jobs WHERE job_key=?',(key,)).fetchone()
    if not j or j['state']!='running':raise ValueError('Running job required')
    d.execute('UPDATE mm_jobs SET state=?,checkpoint=?,lease_until=NULL,updated_at=?,error=? WHERE job_key=?',('failed' if error else 'completed',json.dumps(checkpoint),now(),error,key))
    # Jobs never advance a CRM stage; the operator must pass all independent gates.

REPLY_ACTIONS={'positive':'Human reviews interest and drafts a reply','question':'Human answers the specific question','price_objection':'Review scope and price evidence before drafting','not_now':'Record requested timing; no automatic contact','already_have_provider':'Respect existing provider; no automatic follow-up','wrong_person':'Verify a new contact source before any draft','not_interested':'Suppress address; no further contact','unsubscribe':'Suppress address; no further contact','hostile':'Suppress address; no further contact','bounce':'Suppress address and investigate address quality'}

HUMAN_REPLY_CLASSES=frozenset(REPLY_ACTIONS)-{'bounce'}

def human_reply_verified(d,mid,bid,classification):
    from mm_core import receipt
    if classification not in HUMAN_REPLY_CLASSES:return False
    for row in d.execute("SELECT id FROM mm_receipts WHERE kind='reply' AND object_id=? AND business_id=?",(mid,bid)):
        try:receipt(d,row[0],'reply',bid,mid);return True
        except ValueError:continue
    return False

def record_reply(d,mid,classification,rid):
    from mm_core import receipt,change_stage,digest
    if classification not in REPLY_ACTIONS:raise ValueError('Unknown reply class')
    if classification=='bounce':raise ValueError('Generic bounce is ambiguous: use outreach-dsn, verify provider evidence, and suppress only a confirmed invalid destination. Policy and temporary failures need a hold and investigation.')
    m=d.execute('SELECT * FROM mm_messages WHERE id=?',(mid,)).fetchone()
    if not m or not m['sent_at']:raise ValueError('Verified sent message required')
    receipt(d,m['send_receipt'],'send',m['business_id'],mid,digest(m['recipient'],m['body']))
    receipt(d,rid,'reply',m['business_id'],mid)
    d.execute('UPDATE mm_messages SET reply=? WHERE id=?',(classification,mid))
    stop=classification in ('not_interested','unsubscribe','hostile','bounce')
    if stop:d.execute('INSERT OR IGNORE INTO mm_suppression(address, reason, created_at) VALUES(?,?,?)',(m['recipient'],classification,now()))
    change_stage(d,m['business_id'],'SUPPRESSED' if stop else 'REPLIED',REPLY_ACTIONS[classification])
    event(d,'verified_reply',m['business_id'],classification)

def learn(d):
    from mm_core import receipt,digest
    # Only externally evidenced messages are denominators. Legacy send claims excluded.
    rows=[dict(r) for r in d.execute('SELECT x.*,m.reply,m.business_id AS bid FROM mm_experiments x JOIN mm_messages m ON m.id=x.message_id JOIN mm_receipts r ON cast(r.id AS TEXT)=m.send_receipt WHERE m.sent_at IS NOT NULL AND r.kind=\'send\'')]
    valid=[]
    for row in rows:
        m=d.execute('SELECT * FROM mm_messages WHERE id=?',(row['message_id'],)).fetchone()
        try:receipt(d,m['send_receipt'],'send',m['business_id'],m['id'],digest(m['recipient'],m['body']));valid.append(row)
        except ValueError:continue
    rows=valid
    output={'verified_observations':len(rows),'minimum_per_cohort':30,'winners':[],'segments':{},'most_common_objection':None,'stop':['Do not promote patterns from unsupported sends or tiny samples'],'double_down':[],'basis':'Recorded externally evidenced sends, replies and payments only'}
    for dim in ('industry','problem','offer','price_band','style','demo_type','variant'):
        groups={}
        for r in rows:
            g=groups.setdefault(r[dim],{'sent':0,'replies':0,'positive':0});g['sent']+=1
            if human_reply_verified(d,r['message_id'],r['bid'],r['reply']):g['replies']+=1;g['positive']+=r['reply']=='positive'
        for g in groups.values():
            n=g['sent'];p=g['positive']/n;z=1.96;den=1+z*z/n
            center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
            g['positive_rate_95pct_interval']=[round(max(0,center-half),3),round(min(1,center+half),3)]
            g['eligible_for_comparison']=n>=30
        output['segments'][dim]=groups
    output['conclusion']='Insufficient actual outcomes to identify winners' if len(rows)<60 else 'Review cohort sizes and uncertainty; no automatic promotion'
    output['ev_per_hour_niche']='Not established: measured sales/delivery hours unavailable'
    return output


def assign_experiment(d,mid,industry,problem,offer,price_band,style,demo_type):
    m=d.execute('SELECT * FROM mm_messages WHERE id=?',(mid,)).fetchone()
    if not m or m['sent_at'] or m['invalidated_reason']:raise ValueError('Valid unsent draft required for experiment assignment')
    eligible(d,m['business_id'],m['recipient'])
    if problem not in ONTOLOGY:raise ValueError('Known problem type required')
    existing=d.execute('SELECT * FROM mm_experiments WHERE message_id=?',(mid,)).fetchone()
    if existing:return dict(existing)
    variant='A' if int(sha(str(m['business_id'])+problem)[:8],16)%2==0 else 'B'
    d.execute('INSERT INTO mm_experiments(business_id,message_id,industry,problem,offer,price_band,style,demo_type,variant,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(m['business_id'],mid,industry,problem,offer,price_band,style,demo_type,variant,now()))
    return dict(d.execute('SELECT * FROM mm_experiments WHERE message_id=?',(mid,)).fetchone())
