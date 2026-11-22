# Issue #138: Schedule Health Failure Analysis

## GitHub Actions Run: 44730550549
- **Workflow**: Durable Cloud Draft Pipeline (cloud-prospect-pipeline.yml)
- **Failed Job**: verify-schedule (not present in current workflows)
- **Expected Schedule**: Friday 20 November 2026, 04:50 UTC (cron: '50 4 * * 2,5')

## Current Workflow Configuration

### Schedule
- **Cron**: `50 4 * * 2,5` (Tuesdays and Fridays at 04:50 UTC)
- **Branch**: master only
- **Concurrency**: `durable-cloud-draft-pipeline`, `cancel-in-progress: false`

### Activation Requirements
The `draft-pipeline` job only runs when:
1. `github.event_name != 'pull_request'`
2. `github.ref == 'refs/heads/master'`
3. `vars.WA_PIPELINE_ENABLED == 'true'`

### Checkpoint Restoration
The `cloud_pipeline_checkpoint.py` script:
- Looks for prior runs with event type "schedule" or "workflow_dispatch"
- Verifies run metadata: head_branch=master, event in {schedule, workflow_dispatch}, correct workflow path
- Selects latest run where "draft-pipeline" job wasn't skipped
- Downloads and validates the `pipeline-state` artifact

## Potential Root Causes for Missed Scheduled Run

### 1. WA_PIPELINE_ENABLED not set to true (Most Likely)
If `WA_PIPELINE_ENABLED` variable is not set to `true`, the scheduled run will be skipped (not failed). The configuration job explicitly checks this and fails with a clear message for manual dispatches, but for scheduled runs it would just skip the job.

### 2. WA_PIPELINE_STATE_KEY not configured
If the secret `WA_PIPELINE_STATE_KEY` is not configured, the configuration job would fail, preventing the draft-pipeline job from running.

### 3. GitHub Actions Schedule Limitations
- Scheduled runs can be delayed by several minutes to hours
- GitHub may skip scheduled runs for inactive repositories (no activity for 60+ days)
- The repository must have at least one workflow run in the last 60 days for schedules to fire

### 4. Concurrency Queue Blocking
With `cancel-in-progress: false`, if a previous run is still running, the scheduled run will queue. If the previous run hangs, it blocks subsequent runs.

### 5. Missing/Expired Checkpoint Artifact
If the prior run failed to upload the `pipeline-state` artifact, the checkpoint restoration would fail.

## Verification Steps Required (Owner Action Needed)

1. **Check GitHub Variables**: Verify `WA_PIPELINE_ENABLED=true` is set in repository variables
2. **Check GitHub Secrets**: Verify `WA_PIPELINE_STATE_KEY` is configured
3. **Check Repository Activity**: Ensure repository has recent activity (last 60 days)
4. **Check Run History**: Look for scheduled runs on master branch around 2026-11-20 04:50 UTC
5. **Distinguish Trigger Types**: Verify the run was schedule-triggered, not push/manual

## Current Status
- **Workflow Configuration**: ✓ Correct (cron, branch, concurrency)
- **Checkpoint Restoration Logic**: ✓ Verifies schedule/workflow_dispatch events
- **WA_PIPELINE_ENABLED**: ⚠️ Unknown - requires owner verification
- **WA_PIPELINE_STATE_KEY**: ⚠️ Unknown - requires owner verification
- **Schedule Execution**: ⚠️ Unknown - requires GitHub Actions history access

## Recommendation
The most likely cause is that `WA_PIPELINE_ENABLED` is not set to `true`, causing scheduled runs to be skipped. The "verify-schedule" job (if it existed) would detect this by checking for missing schedule-triggered runs.

Since the job "verify-schedule" is not present in current workflows, it may have been a separate monitoring workflow that was removed or is in a different branch.

**Action Required**: Owner to verify GitHub repository variables and secrets configuration.
