"""Named transactional operations shared by persistence failure tests."""


import pytest

from scripts import cloud_prospect_pipeline as pipeline


def assert_replay_sends_no_requests(store, workspace):
    def forbidden(*args):
        pytest.fail("Interrupted reservation sent a second request")

    for now in (0, 86400):
        with store.transaction() as state:
            pipeline.process(
                state,
                [dict(domain="example.com", url="https://example.com")],
                now=now,
                run_id=f"replay-{now}",
                workspace=workspace,
                attempt_reserver=store.reserve_attempt,
                robots=forbidden,
                audit=forbidden,
            )
        assert store.operational_summary()["reservations"] == 1
    assert store.read()["audit_runs"] == []


def assert_committed_attempt_allows_retry(store, workspace):
    calls = []

    def audit(*args):
        calls.append(True)
        return [{"status": "INCOMPLETE"}]

    for now, expected_attempts in ((0, 1), (3599, 1), (3600, 2)):
        with store.transaction() as state:
            pipeline.process(
                state,
                [dict(domain="example.com", url="https://example.com")],
                now=now,
                run_id=f"attempt-{now}",
                workspace=workspace,
                attempt_reserver=store.reserve_attempt,
                robots=lambda _: True,
                audit=audit,
            )
        assert len(calls) == expected_attempts
        assert store.operational_summary()["reservations"] == expected_attempts
        assert len(store.read()["audit_runs"]) == expected_attempts


def commit_mutation(store, mutate, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap) as state:
        mutate(state)


def interrupt_reserved_transaction(store, prospect_id, audit_id, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap):
        assert store.reserve_attempt(prospect_id, audit_id, now=0, daily_limit=6)
        raise RuntimeError("Synthetic interruption before queue commit")
