"""Compatibility module for mm_operator commands.

Re-exports all functions from the original mm_operator.py and other modules
to provide a unified import interface for command modules.
"""

from __future__ import annotations

# Core functions from mm_operator.py
from mm_operator import (
    run_day,
    learn,
    doctor,
    assign_experiment,
    pricing,
    demo_qa,
    claim_job,
    finish_job,
    model_request,
    cmd_dead_letter_resolve,
    cmd_data_quarantine,
    backup,
    validate_environment,
    root,
    OperatorError,
    ValidationError,
    OperationalError,
    REPLY_ACTIONS,
    STAGES,
    CLAIM_TYPES,
    ONTOLOGY,
    OFFERS,
    atomic_write,
    public_url,
    sha,
    now as mm_now,
)

# Functions from mm_core
from mm_core import (
    business,
    eligible,
    latest_evidence,
    fresh,
    event,
    change_stage,
    create_draft,
    approve,
    record_sent,
    import_receipt,
    cash,
    refund,
    create_proposal,
    record_evidence,
    record_contact,
    connect,
    CLAIM_TYPES as MM_CLAIM_TYPES,
    STAGES as MM_STAGES,
)

# Functions from mm_intelligence
from mm_intelligence import (
    REPLY_ACTIONS,
    OFFERS,
    ONTOLOGY,
    score,
    save_score,
    human_reply_verified,
    record_reply,
    pricing as int_pricing,
    model_request,
    claim_job,
    finish_job,
    learn as int_learn,
    assign_experiment,
)

# Functions from mm_drafts
from mm_drafts import review_draft, approve_draft

# Re-exports for backward compatibility
CLAIM_TYPES = CLAIM_TYPES
STAGES = STAGES
REPLY_ACTIONS = REPLY_ACTIONS
OFFERS = OFFERS
ONTOLOGY = ONTOLOGY
mm_now = mm_now

# Alias for mm_operator functions
run_day = run_day
learn = learn
doctor = doctor
assign_experiment = assign_experiment
pricing = pricing
demo_qa = demo_qa
claim_job = claim_job
finish_job = finish_job
model_request = model_request
cmd_dead_letter_resolve = cmd_dead_letter_resolve
cmd_data_quarantine = cmd_data_quarantine
backup = backup
validate_environment = validate_environment
root = root
OperatorError = OperatorError
ValidationError = ValidationError
OperationalError = OperationalError
REPLY_ACTIONS = REPLY_ACTIONS
STAGES = STAGES
CLAIM_TYPES = CLAIM_TYPES
ONTOLOGY = ONTOLOGY
OFFERS = OFFERS
atomic_write = atomic_write
public_url = public_url
sha = sha
mm_now = mm_now

# mm_core functions
business = business
eligible = eligible
latest_evidence = latest_evidence
fresh = fresh
event = event
change_stage = change_stage
create_draft = create_draft
approve = approve
record_sent = record_sent
import_receipt = import_receipt
cash = cash
refund = refund
create_proposal = create_proposal
record_evidence = record_evidence
record_contact = record_contact
connect = connect

# mm_intelligence functions
REPLY_ACTIONS = REPLY_ACTIONS
OFFERS = OFFERS
ONTOLOGY = ONTOLOGY
score = score
save_score = save_score
human_reply_verified = human_reply_verified
record_reply = record_reply
pricing = pricing
model_request = model_request
claim_job = claim_job
finish_job = finish_job
learn = learn
assign_experiment = assign_experiment
demo_qa = demo_qa