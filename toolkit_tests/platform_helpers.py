"""Named transactional operations shared by persistence failure tests."""


def commit_mutation(store, mutate, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap) as state:
        mutate(state)


def interrupt_reserved_transaction(store, prospect_id, audit_id, *, bootstrap=False):
    with store.transaction(bootstrap=bootstrap):
        assert store.reserve_attempt(prospect_id, audit_id, now=0, daily_limit=6)
        raise RuntimeError("Synthetic interruption before queue commit")
