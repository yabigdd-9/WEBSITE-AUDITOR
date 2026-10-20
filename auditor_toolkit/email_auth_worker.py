"""Owned DNS-only checker worker; imported/executed only when explicitly requested."""

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from importlib import metadata

from .email_auth import (
    CHECKER_VERSION,
    MAX_OUTPUT_BYTES,
    MAX_QUERY_CALLS,
    MAX_SECONDS,
    normalize_domain,
    unknown_result,
)


def make_resolver(deadline):
    import dns.exception
    import dns.rdatatype
    import dns.resolver

    class BudgetExceeded(dns.exception.DNSException):
        pass

    class BudgetedResolver(dns.resolver.Resolver):
        def __init__(self):
            super().__init__()
            self.calls = []
            self.rejected_calls = 0
            self.current_protocol = None
            self.timeout = 0.5
            self.lifetime = 2.0
            self.use_search_by_default = False

        def resolve(self, qname, rdtype="A", *args, **kwargs):
            kind = rdtype.upper() if isinstance(rdtype, str) else dns.rdatatype.to_text(rdtype)
            row = {"name": str(qname).rstrip(".").lower(), "type": kind,
                   "protocol": self.current_protocol, "status": "pending", "material": True}
            remaining = deadline - time.monotonic()
            if remaining <= 0 or len(self.calls) >= MAX_QUERY_CALLS:
                self.rejected_calls += 1
                raise BudgetExceeded("Shared DNS time or resolver-call budget exhausted")
            self.calls.append(row)
            kwargs["lifetime"] = min(2.0, remaining)
            kwargs["search"] = False
            try:
                answer = super().resolve(qname, rdtype, *args, **kwargs)
                records = [str(record) for record in answer]
                payload = json.dumps(records, ensure_ascii=True).encode()
                row.update(status="ok", answer_count=len(records),
                           answer_sha256=hashlib.sha256(payload).hexdigest())
                return answer
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as exc:
                row.update(status="no_answer" if isinstance(exc, dns.resolver.NoAnswer) else "nxdomain")
                raise
            except Exception as exc:
                row.update(status="lookup_error", error_type=type(exc).__name__)
                # Deprecated SPF RR failures do not taint the authoritative TXT check.
                # Other lookup failures conservatively taint validity.
                row["material"] = not (self.current_protocol == "spf" and kind == "SPF")
                raise

    return BudgetedResolver()


def protocol_result(check, domain, resolver, deadline):
    first = len(resolver.calls)
    rejected = resolver.rejected_calls
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"status": "unknown", "valid": None, "reason": "shared_deadline_exceeded"}
        raw = check(domain, resolver=resolver, timeout=min(2.0, remaining), retries=0)
    except Exception as exc:
        return {"status": "unknown", "valid": None, "reason": "checker_exception",
                "error_type": type(exc).__name__}
    if not isinstance(raw, dict) or type(raw.get("valid")) is not bool:
        return {"status": "unknown", "valid": None, "reason": "invalid_checker_schema"}
    if raw["valid"]:
        valid_record = isinstance(raw.get("record"), str) and bool(raw["record"])
        if resolver.current_protocol == "spf":
            valid_record = valid_record and isinstance(raw.get("parsed"), dict)
        else:
            valid_record = (valid_record and isinstance(raw.get("tags"), dict)
                            and isinstance(raw.get("location"), str) and bool(raw["location"]))
        if not valid_record or raw.get("error"):
            return {"status": "unknown", "valid": None, "reason": "invalid_checker_schema"}
    elif not isinstance(raw.get("error"), str) or not raw["error"]:
        return {"status": "unknown", "valid": None, "reason": "invalid_checker_schema"}
    failures = [row for row in resolver.calls[first:]
                if row["status"] == "lookup_error" and row["material"]]
    bounded = resolver.rejected_calls != rejected or time.monotonic() >= deadline
    if failures or bounded:
        return {"status": "unknown", "valid": None,
                "reason": "dns_lookup_error" if failures else "shared_budget_exhausted",
                "reported_valid": raw["valid"], "checker_result": raw}
    # Preserve checker conclusions/errors/policy tags; no independent message claim.
    return {"status": "validated_record" if raw["valid"] else "checker_rejected",
            "valid": raw["valid"], "reported_valid": raw["valid"], "checker_result": raw}


def main():
    request = json.loads(sys.stdin.buffer.read(8193))
    domain = normalize_domain(request["domain"])
    timeout = request["timeout"]
    if type(timeout) not in {int, float} or not 1 <= timeout <= MAX_SECONDS:
        raise ValueError("Invalid worker timeout")
    deadline = time.monotonic() + timeout
    result = unknown_result(domain, "checker_unavailable")
    installed = metadata.version("checkdmarc")
    result["checker"]["version"] = installed
    if installed != CHECKER_VERSION:
        raise ValueError("Unsupported checker version")
    # Selected APIs only. check_domains includes unrelated services.
    from checkdmarc.dmarc import check_dmarc
    from checkdmarc.spf import check_spf

    resolver = make_resolver(deadline)
    for name, check in (("spf", check_spf), ("dmarc", check_dmarc)):
        resolver.current_protocol = name
        result[name] = protocol_result(check, domain, resolver, deadline)
    result["checked_at_utc"] = datetime.now(UTC).isoformat()
    result["dns_queries"] = resolver.calls
    result["limits"] = {"seconds": timeout, "resolver_calls": MAX_QUERY_CALLS,
                        "resolver_calls_used": len(resolver.calls),
                        "rejected_calls": resolver.rejected_calls, "retries": 0,
                        "scope": "Resolver API calls, not an exact DNS packet count"}
    raw = json.dumps(result, ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > MAX_OUTPUT_BYTES:
        result = unknown_result(domain, "checker_output_limit")
        result["checker"]["version"] = installed
        raw = json.dumps(result).encode()
    sys.stdout.buffer.write(raw)


if __name__ == "__main__":
    main()
