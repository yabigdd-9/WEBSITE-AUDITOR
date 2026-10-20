# Current synthetic canonical-schema restore drill

A fresh SQLite copy was created from the versioned-schema/migration synthetic
fixture used by the baseline. No production records were opened or copied.
The existing D10 probe exercised WAL-aware mm_core.backup, restore integrity,
complete dump equality, planned/quarantined records and suppression preservation.
An interrupted restore exited 17 and was rejected; source and backup remained intact.
See [the timestamped receipt](completion-20261020/d10-canonical-receipt.json).
This is fixture acceptance, not independent release approval, production rollback
acceptance or an RPO/RTO guarantee.
