"""Downloads must authorize before touching files and redact filesystem failures."""

import hashlib
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from auditor_toolkit.portal import OwnerPortal


def portal():
    app = SimpleNamespace(state=SimpleNamespace(sessions={}))
    return OwnerPortal(app, None, None, "unused", 3600, None)


def test_download_denies_session_before_resolving_private_file():
    owner = portal()

    def forbidden():
        pytest.fail("Unauthenticated request reached private filesystem")

    with pytest.raises(HTTPException) as error:
        owner.download(SimpleNamespace(cookies={}), forbidden, "Artifact unavailable")
    assert error.value.status_code == 401


def test_download_redacts_private_filesystem_errors():
    owner = portal()
    token = "synthetic-session"
    owner.app.state.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
        "expires": time.time() + 60, "csrf": "synthetic-csrf",
    }

    def unavailable():
        raise PermissionError("private/path/owner-archive.enc")

    request = SimpleNamespace(cookies={"wa_session": token})
    with pytest.raises(HTTPException) as error:
        owner.download(request, unavailable, "Artifact unavailable")
    assert error.value.status_code == 404
    assert error.value.detail == "Artifact unavailable"
