"""Tests for the bearer-token authentication helpers."""

from __future__ import annotations

import pytest

from apex_mcp_server.auth import StaticBearerTokenVerifier


@pytest.mark.asyncio
async def test_static_bearer_token_verifier_accepts_matching_token() -> None:
    """Ensure the configured bearer token is accepted.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If a matching token is rejected.
    """

    verifier = StaticBearerTokenVerifier(api_token="demo-token")

    token = await verifier.verify_token("demo-token")

    assert token is not None
    assert token.client_id == "static-bearer"
    assert token.claims == {"sub": "private-profile", "auth_type": "bearer"}


@pytest.mark.asyncio
async def test_static_bearer_token_verifier_rejects_mismatched_token() -> None:
    """Ensure the verifier rejects the wrong bearer token.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If a mismatched token is accepted.
    """

    verifier = StaticBearerTokenVerifier(api_token="demo-token")

    token = await verifier.verify_token("wrong-token")

    assert token is None
