# Login rate-limit policy

Catalyx applies two persistent limits before credential verification:

- **Per client address:** 8 login attempts per minute.
- **Shared application budget:** 60 attempts per minute by default, configurable
  downward with `CATALYX_LOGIN_GLOBAL_LIMIT_PER_MINUTE` to an integer from 1
  through 60.

The shared budget uses one hashed subject in the application database. It
limits aggregate password-hash work across account names and client addresses
when all application instances use the same database. Configuration outside
the accepted range prevents startup. No secret is required to set this limit,
and no `.env` file is required.

The shared budget protects authentication capacity without blocking a specific
account after distributed failed logins. When the shared budget is exhausted,
all login attempts, including valid credentials, receive a temporary `429`
response until the minute window resets. The default and any deployed value are
provisional operating thresholds; the owner must approve the capacity and
recovery behavior before public authentication is enabled. This does not
replace trusted client-address handling at the selected hosting edge.

Verification-resend and password-reset email limits remain separate. Hosted
mail and live external sends remain disabled by default and require their
existing explicit gates.

Each rate-limited request removes at most 100 expired subject buckets. It
cleans the active scope against that scope's window and also sweeps older rows
from any scope once their last update is at least one hour old. This lets
requests in other scopes drain dormant buckets while bounding delete work per
request. Cleanup is opportunistic: if no rate-limited requests occur, expired
rows remain until the next such request. Update the one-hour maximum if a
longer authentication window is introduced. The retention period and any
production scheduled cleanup remain owner/architecture decisions.
