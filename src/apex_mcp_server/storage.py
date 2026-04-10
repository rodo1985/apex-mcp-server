"""Profile storage backends for local files and Vercel Blob."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from vercel.blob import AsyncBlobClient

from apex_mcp_server.config import Settings
from apex_mcp_server.models import SaveResult


class ProfileStore(ABC):
    """Define the read/write contract for profile persistence backends.

    Parameters:
        None.

    Returns:
        ProfileStore: An abstract interface implemented by concrete backends.

    Raises:
        This abstract base class does not raise errors directly.

    Example:
        >>> isinstance(ProfileStore.__mro__[0], type)
        True
    """

    @abstractmethod
    async def read(self, user_key: str) -> str:
        """Read the profile markdown for a stable user key.

        Parameters:
            user_key: Stable storage key for the profile owner.

        Returns:
            str: Markdown profile content, or an empty string when missing.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """

    @abstractmethod
    async def write(self, user_key: str, markdown: str) -> SaveResult:
        """Overwrite the profile markdown for a stable user key.

        Parameters:
            user_key: Stable storage key for the profile owner.
            markdown: New profile markdown to persist.

        Returns:
            SaveResult: Summary of the write operation.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """


class FileProfileStore(ProfileStore):
    """Persist profile markdown files on the local filesystem.

    Parameters:
        root_dir: Directory that contains local profile markdown files.

    Returns:
        FileProfileStore: A storage backend suitable for local development.

    Raises:
        OSError: Raised by filesystem operations when permissions or paths fail.

    Example:
        >>> FileProfileStore(Path("profiles"))._path_for("anonymous").name
        'anonymous.md'
    """

    def __init__(self, root_dir: Path):
        """Initialize the local file-backed store.

        Parameters:
            root_dir: Directory used for local profile files.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.

        Example:
            >>> FileProfileStore(Path("profiles"))
            <apex_mcp_server.storage.FileProfileStore object ...>
        """

        self.root_dir = root_dir

    async def read(self, user_key: str) -> str:
        """Read the markdown file for a user from local disk.

        Parameters:
            user_key: Stable storage key for the profile owner.

        Returns:
            str: Stored markdown, or an empty string if the file does not exist.

        Raises:
            OSError: If the file exists but cannot be read.

        Example:
            >>> import asyncio
            >>> store = FileProfileStore(Path("profiles"))
            >>> asyncio.run(store.read("missing")) == ""
            True
        """

        path = self._path_for(user_key)
        if not path.exists():
            return ""

        # The pilot stores one small markdown file per user, so straightforward
        # blocking file I/O keeps the code easy to read for new contributors.
        return path.read_text(encoding="utf-8")

    async def write(self, user_key: str, markdown: str) -> SaveResult:
        """Overwrite the markdown file for a user on local disk.

        Parameters:
            user_key: Stable storage key for the profile owner.
            markdown: Markdown content to persist.

        Returns:
            SaveResult: Summary of the completed write.

        Raises:
            OSError: If the file cannot be written.

        Example:
            >>> import asyncio, tempfile
            >>> temp = Path(tempfile.mkdtemp())
            >>> store = FileProfileStore(temp)
            >>> asyncio.run(store.write("demo", "# Demo")).saved
            True
        """

        path = self._path_for(user_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = markdown.encode("utf-8")
        path.write_bytes(encoded)
        return SaveResult(saved=True, pathname=str(path), bytes=len(encoded))

    def _path_for(self, user_key: str) -> Path:
        """Build the local file path for a user profile.

        Parameters:
            user_key: Stable storage key for the profile owner.

        Returns:
            Path: Local markdown file path.

        Raises:
            This helper does not raise errors directly.

        Example:
            >>> path = FileProfileStore(Path("profiles"))._path_for("demo")
            >>> path.as_posix().endswith("demo.md")
            True
        """

        return self.root_dir / f"{user_key}.md"


class BlobProfileStore(ProfileStore):
    """Persist profile markdown documents in a private Vercel Blob store.

    Parameters:
        prefix: Blob pathname prefix used for all profile documents.
        client: Async Vercel Blob client.

    Returns:
        BlobProfileStore: A storage backend suitable for deployed Vercel usage.

    Raises:
        Exception: The underlying Blob SDK may raise network or auth errors.

    Example:
        >>> store = BlobProfileStore(prefix="profiles", client=AsyncBlobClient())
        >>> store._path_for("demo")
        'profiles/demo.md'
    """

    def __init__(self, prefix: str, client: AsyncBlobClient):
        """Initialize the Blob-backed store.

        Parameters:
            prefix: Blob pathname prefix used for all profile documents.
            client: Async Vercel Blob client.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.

        Example:
            >>> BlobProfileStore(prefix="profiles", client=AsyncBlobClient())
            <apex_mcp_server.storage.BlobProfileStore object ...>
        """

        self.prefix = prefix.strip("/")
        self.client = client

    async def read(self, user_key: str) -> str:
        """Read the markdown document for a user from Vercel Blob.

        Parameters:
            user_key: Stable storage key for the profile owner.

        Returns:
            str: Stored markdown, or an empty string if the blob is missing.

        Raises:
            Exception: Propagated from the Blob SDK when the request fails.

        Example:
            >>> store = BlobProfileStore("profiles", AsyncBlobClient())
            >>> store._path_for("demo")
            'profiles/demo.md'
        """

        result = await self.client.get(self._path_for(user_key), access="private")
        if result is None or result.status_code != 200:
            return ""

        chunks: list[bytes] = []
        async for chunk in result.stream:
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")

    async def write(self, user_key: str, markdown: str) -> SaveResult:
        """Overwrite the markdown document for a user in Vercel Blob.

        Parameters:
            user_key: Stable storage key for the profile owner.
            markdown: Markdown content to persist.

        Returns:
            SaveResult: Summary of the completed write.

        Raises:
            Exception: Propagated from the Blob SDK when the upload fails.

        Example:
            >>> store = BlobProfileStore("profiles", AsyncBlobClient())
            >>> store._path_for("demo")
            'profiles/demo.md'
        """

        encoded = markdown.encode("utf-8")
        result = await self.client.put(
            self._path_for(user_key),
            encoded,
            access="private",
            content_type="text/markdown; charset=utf-8",
            overwrite=True,
        )
        return SaveResult(saved=True, pathname=result.pathname, bytes=len(encoded))

    def _path_for(self, user_key: str) -> str:
        """Build the blob pathname for a user profile.

        Parameters:
            user_key: Stable storage key for the profile owner.

        Returns:
            str: Blob pathname under the configured prefix.

        Raises:
            This helper does not raise errors directly.

        Example:
            >>> BlobProfileStore("profiles", AsyncBlobClient())._path_for("demo")
            'profiles/demo.md'
        """

        return f"{self.prefix}/{user_key}.md"


def build_profile_store(settings: Settings) -> ProfileStore:
    """Create the configured profile storage backend.

    Parameters:
        settings: Normalized runtime settings.

    Returns:
        ProfileStore: Either the local file store or the Vercel Blob store.

    Raises:
        Exception: Propagated if backend initialization fails.

    Example:
        >>> isinstance(build_profile_store(Settings.from_env()), ProfileStore)
        True
    """

    if settings.profile_storage_backend == "blob":
        return BlobProfileStore(
            prefix=settings.blob_prefix,
            client=AsyncBlobClient(token=settings.blob_read_write_token),
        )

    return FileProfileStore(root_dir=settings.profiles_dir)
