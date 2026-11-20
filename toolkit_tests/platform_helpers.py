"""Named transactional operations shared by persistence failure tests."""


import pytest

from scripts import cloud_prospect_pipeline as pipeline


def assert_replay_sends_no_requests(store, workspace):
    def forbidden(*args):
        pytest.fail("Interrupted reservation sent a second request")

    with store.transaction() as state:
        pipeline.process(
            state,
            [dict(domain="example.com", url="https://example.com")],
            now=86400,
            run_id="different-run",
            workspace=workspace,
            attempt_reserver=store.reserve_attempt,
            robots=forbidden,
            audit=forbidden,
        )
    assert store.read()["audit_runs"] == []


def commit_mutation(store, mutate, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap) as state:
        mutate(state)


def interrupt_reserved_transaction(store, prospect_id, audit_id, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap):
        assert store.reserve_attempt(prospect_id, audit_id, now=0, daily_limit=6)
        raise RuntimeError("Synthetic interruption before queue commit")
