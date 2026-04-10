"""Tests for the profile storage backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from apex_mcp_server.storage import BlobProfileStore, FileProfileStore


@pytest.mark.asyncio
async def test_file_profile_store_round_trip(tmp_path: Path) -> None:
    """Ensure the local file store can write and read markdown profiles.

    Parameters:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        None.

    Raises:
        AssertionError: If the storage round trip does not match expectations.
    """

    store = FileProfileStore(tmp_path)

    missing_profile = await store.read("anonymous")
    save_result = await store.write("anonymous", "# Persona\nHelpful")
    loaded_profile = await store.read("anonymous")

    assert missing_profile == ""
    assert save_result.saved is True
    assert save_result.bytes == len(b"# Persona\nHelpful")
    assert loaded_profile == "# Persona\nHelpful"


@pytest.mark.asyncio
async def test_blob_profile_store_round_trip() -> None:
    """Ensure the Blob store uses the expected path and payload shape.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the mocked Blob interactions differ from expectations.
    """

    client = StubBlobClient()
    store = BlobProfileStore(prefix="profiles", client=client)

    missing_profile = await store.read("github-1")
    save_result = await store.write("github-1", "# Persona\nBlob")
    loaded_profile = await store.read("github-1")

    assert missing_profile == ""
    assert save_result.pathname == "profiles/github-1.md"
    assert save_result.saved is True
    assert loaded_profile == "# Persona\nBlob"
    assert client.saved_payloads["profiles/github-1.md"] == b"# Persona\nBlob"


@dataclass
class StubPutResult:
    """Return value used by the Blob client stub.

    Parameters:
        pathname: Pathname reported back by the mock upload.

    Returns:
        StubPutResult: Minimal stand-in for the SDK upload result.
    """

    pathname: str


class StubBlobReadResult:
    """Minimal async blob read result used by the tests.

    Parameters:
        payload: Bytes that should be returned from the async stream.
        status_code: HTTP-like status code returned by the read operation.

    Returns:
        StubBlobReadResult: A small test double for the Vercel Blob SDK.
    """

    def __init__(self, payload: bytes, status_code: int = 200) -> None:
        """Store the payload used by the fake stream response.

        Parameters:
            payload: Bytes that should be yielded by the response stream.
            status_code: HTTP-like status code for the read call.

        Returns:
            None.
        """

        self._payload = payload
        self.status_code = status_code

    @property
    def stream(self):  # type: ignore[override]
        """Return an async iterator over the stored payload.

        Parameters:
            None.

        Returns:
            object: An async generator that yields one chunk.

        Raises:
            This property does not raise errors directly.
        """
        return self._iterate()

    async def _iterate(self):
        """Yield the stored payload as a single async stream chunk.

        Parameters:
            None.

        Returns:
            object: An async generator that yields the stored payload once.

        Raises:
            This helper does not raise errors directly.
        """

        yield self._payload


class StubBlobClient:
    """Small async client stub that mimics the Blob SDK methods we use.

    Parameters:
        None.

    Returns:
        StubBlobClient: In-memory test double for `AsyncBlobClient`.
    """

    def __init__(self) -> None:
        """Initialize the in-memory payload map used by the stub.

        Parameters:
            None.

        Returns:
            None.
        """

        self.saved_payloads: dict[str, bytes] = {}

    async def get(self, url_or_path: str, *, access: str = "private") -> object | None:
        """Return a blob-like response for the requested path.

        Parameters:
            url_or_path: Blob path requested by the store.
            access: Requested blob access mode.

        Returns:
            object | None: A fake read result or `None` if missing.

        Raises:
            AssertionError: If the store asks for a non-private blob.
        """

        assert access == "private"
        payload = self.saved_payloads.get(url_or_path)
        if payload is None:
            return None
        return StubBlobReadResult(payload=payload)

    async def put(
        self,
        path: str,
        body: bytes,
        *,
        access: str = "private",
        content_type: str | None = None,
        overwrite: bool = False,
    ) -> StubPutResult:
        """Store uploaded bytes in memory and return a fake result object.

        Parameters:
            path: Blob pathname requested by the store.
            body: Uploaded bytes payload.
            access: Requested blob access mode.
            content_type: Requested content type.
            overwrite: Whether overwrite mode is enabled.

        Returns:
            StubPutResult: A fake upload result containing the saved pathname.

        Raises:
            AssertionError: If the store uses the wrong access mode or forgets
                overwrite support.
        """

        assert access == "private"
        assert overwrite is True
        assert content_type == "text/markdown; charset=utf-8"
        self.saved_payloads[path] = body
        return StubPutResult(pathname=path)
