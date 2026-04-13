"""FastMCP server assembly for the profile pilot."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.prompts import Message, PromptResult

from apex_mcp_server.auth import build_auth_provider
from apex_mcp_server.config import Settings
from apex_mcp_server.identity import resolve_identity
from apex_mcp_server.models import UserData
from apex_mcp_server.storage import UserStore, build_user_store

CURRENT_CONTEXT = CurrentContext()


def create_mcp_server(
    settings: Settings | None = None,
    store: UserStore | None = None,
) -> FastMCP:
    """Create the FastMCP server with tools, resource, and prompt.

    Parameters:
        settings: Optional pre-built runtime settings.
        store: Optional store override, mainly useful in tests.

    Returns:
        FastMCP: A fully configured MCP server instance.

    Raises:
        SettingsError: Propagated if runtime settings are invalid.
        ValueError: Propagated if FastMCP rejects server configuration.

    Example:
        >>> server = create_mcp_server()
        >>> server.name
        'APEX FastMCP Profile Pilot'
    """

    resolved_settings = settings or Settings.from_env()
    resolved_store = store or build_user_store(resolved_settings)

    mcp = FastMCP(
        name=resolved_settings.app_name,
        version=resolved_settings.version,
        instructions=(
            "A minimal FastMCP pilot that stores one protected markdown persona "
            "profile and a few numeric profile fields in Postgres."
        ),
        auth=build_auth_provider(resolved_settings),
    )

    @mcp.tool
    async def get_profile(ctx: Context = CURRENT_CONTEXT) -> str:
        """Return the caller's current profile markdown.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored profile markdown, or an empty string when no profile has
                been saved yet.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            A connected MCP client can call `get_profile` with no arguments to
            fetch the currently saved profile.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        return await resolved_store.get_profile(identity.storage_subject())

    @mcp.tool
    async def set_profile(
        profile_markdown: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's current profile markdown.

        Parameters:
            profile_markdown: New markdown content for the profile document.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation including `saved`, `subject`,
                and `bytes`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            A connected MCP client can call `set_profile` with a markdown string
            such as `# Persona\\nHelpful and concise.`.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        result = await resolved_store.set_profile(
            identity.storage_subject(),
            profile_markdown,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def get_user_data(ctx: Context = CURRENT_CONTEXT) -> dict[str, object]:
        """Return the caller's saved numeric user data.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Numeric user fields with nullable values.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            A connected MCP client can call `get_user_data` to fetch weight,
            height, and FTP values stored for the current caller.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        data = await resolved_store.get_user_data(identity.storage_subject())
        return data.as_dict()

    @mcp.tool
    async def set_user_data(
        weight_kg: float | None,
        height_cm: float | None,
        ftp_watts: int | None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's saved numeric user data.

        Parameters:
            weight_kg: Body weight in kilograms, or `null`.
            height_cm: Height in centimeters, or `null`.
            ftp_watts: Functional threshold power in watts, or `null`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation plus the stored numeric values.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            A connected MCP client can call `set_user_data(weight_kg=68.5,
            height_cm=174.0, ftp_watts=250)` to persist simple tabular data.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        data = UserData(
            weight_kg=weight_kg,
            height_cm=height_cm,
            ftp_watts=ftp_watts,
        )
        result = await resolved_store.set_user_data(
            identity.storage_subject(),
            data,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def whoami(ctx: Context = CURRENT_CONTEXT) -> dict[str, object]:
        """Return the current caller identity for auth debugging.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Diagnostic identity payload with `authenticated`,
                `subject`, `login`, and `request_id`.

        Raises:
            RuntimeError: If authentication is required but unavailable.

        Example:
            Call `whoami` after connecting a remote MCP client to confirm the
            current bearer-token or OAuth identity wiring.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        return identity.as_whoami_response()

    @mcp.resource(
        "profile://me",
        mime_type="text/markdown",
        annotations={"readOnlyHint": True, "idempotentHint": True},
        description="The current caller's saved profile markdown.",
    )
    async def profile_resource(ctx: Context = CURRENT_CONTEXT) -> str:
        """Expose the current caller's profile as a readable MCP resource.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored profile markdown, or an empty string when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            Read the `profile://me` resource to feed the saved persona into a
            client conversation without calling a tool first.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        return await resolved_store.get_profile(identity.storage_subject())

    @mcp.prompt(
        description="Inject the caller's saved profile into a simple task prompt.",
    )
    async def use_profile(task: str, ctx: Context = CURRENT_CONTEXT) -> PromptResult:
        """Generate a prompt that includes the caller's saved profile.

        Parameters:
            task: Task the downstream LLM should complete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            PromptResult: A single-message prompt enriched with the caller's
                stored profile markdown.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.

        Example:
            Ask for `use_profile(task="Draft a warm onboarding message")` to
            render a prompt that includes the saved persona profile.
        """

        identity = resolve_identity(ctx, resolved_settings.auth_mode)
        profile_markdown = await resolved_store.get_profile(identity.storage_subject())

        if profile_markdown.strip():
            profile_block = profile_markdown
            has_profile = True
        else:
            profile_block = "No profile is saved yet for this caller."
            has_profile = False

        # We keep the prompt intentionally plain so it remains easy to inspect
        # in clients that expose prompt rendering during this pilot.
        return PromptResult(
            messages=[
                Message(
                    "Use the following persona profile while completing the "
                    "task.\n\n"
                    f"Task:\n{task}\n\n"
                    f"Profile:\n{profile_block}"
                )
            ],
            description="Prompt enriched with the caller's saved profile.",
            meta={"has_profile": has_profile},
        )

    return mcp
