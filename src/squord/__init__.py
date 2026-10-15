"""squord.py — o SDK oficial do Squord para criar bots em Python.

Documentação da plataforma: https://docs.squord.com.br

```python
import asyncio
import os

import squord


async def main() -> None:
    client = squord.SquordClient(token=os.environ["SQUORD_BOT_TOKEN"])

    @client.on("message.created")
    async def on_message(message: squord.Message) -> None:
        if message.content == "!ping":
            await message.reply("Pong! 🏓")

    await client.login()


asyncio.run(main())
```
"""

from .builders import (
    COMPONENT_LIMITS,
    EMBED_LIMITS,
    ActionRowBuilder,
    ButtonBuilder,
    Buttons,
    EmbedBuilder,
    SelectMenuBuilder,
    normalize_embed_color,
    resolve_message_edit_payload,
    resolve_message_payload,
    safe_allowed_mentions,
)
from .cache import Cache
from .client import SquordClient
from .commands import (
    CommandRegistry,
    ComponentHandlerDefinition,
    SlashCommandDefinition,
    TextCommandContext,
    TextCommandDefinition,
)
from .enums import (
    AttachmentScanStatus,
    ButtonStyle,
    ChannelType,
    CommandOptionType,
    GuildFlags,
    InteractionCallbackType,
    InteractionType,
    MemberType,
    MessageType,
    PresenceStatus,
    RoleManagedKind,
    ThreadAutoArchiveMinutes,
    UploadStatus,
    UserFlags,
)
from .errors import (
    AuthenticationError,
    GatewayError,
    InvalidTokenError,
    NetworkError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    RequestTimeoutError,
    SquordAPIError,
    SquordError,
    SquordTypeError,
    ValidationError,
    make_api_error,
)
from .gateway import Gateway, WSClosed, aiohttp_ws_connector
from .http import (
    DEFAULT_BASE_URL,
    RequestOptions,
    RestClient,
    RestResponse,
    Transport,
    paginate,
    route_key_of,
)
from .intents import DEFAULT_INTENTS, Intents, intents_value, list_intents
from .logger import get_logger, redact, setup_logging
from .managers import (
    ApplicationCommandsManager,
    BotManager,
    ChannelsManager,
    GuildsManager,
    InteractionsManager,
    MembersManager,
    MessagesManager,
    ModerationManager,
    RolesManager,
    UploadsManager,
    UsersManager,
)
from .models import Channel, Guild, Interaction, Member, Message, Role, Thread, User
from .permissions import (
    ALL_PERMISSIONS,
    SUGGESTED_MODERATION_PERMISSIONS,
    SUGGESTED_TEXT_BOT_PERMISSIONS,
    Permissions,
    has_any_permission,
    has_permissions,
    parse_permissions,
    permissions_to_string,
    resolve_channel_permissions,
)
from .types import (
    AllowedMentions,
    Cursor,
    CursorPaginationParams,
    Snowflake,
    channel_mention,
    role_mention,
    user_mention,
)
from .utils import (
    assert_snowflake,
    backoff_delay,
    compare_snowflakes,
    is_valid_snowflake,
    split_arguments,
)

__version__ = "0.1.0"

__all__ = [
    "ALL_PERMISSIONS",
    "COMPONENT_LIMITS",
    "DEFAULT_BASE_URL",
    "DEFAULT_INTENTS",
    "EMBED_LIMITS",
    "SUGGESTED_MODERATION_PERMISSIONS",
    "SUGGESTED_TEXT_BOT_PERMISSIONS",
    "ActionRowBuilder",
    "AllowedMentions",
    "ApplicationCommandsManager",
    # Enums
    "AttachmentScanStatus",
    "AuthenticationError",
    "BotManager",
    "ButtonBuilder",
    "ButtonStyle",
    "Buttons",
    # Cache, logger, utilidades
    "Cache",
    "Channel",
    "ChannelType",
    "ChannelsManager",
    "CommandOptionType",
    # Comandos
    "CommandRegistry",
    "ComponentHandlerDefinition",
    "Cursor",
    "CursorPaginationParams",
    # Builders
    "EmbedBuilder",
    # Gateway
    "Gateway",
    "GatewayError",
    "Guild",
    "GuildFlags",
    "GuildsManager",
    "Intents",
    "Interaction",
    "InteractionCallbackType",
    "InteractionType",
    "InteractionsManager",
    "InvalidTokenError",
    "Member",
    "MemberType",
    "MembersManager",
    # Modelos
    "Message",
    "MessageType",
    # Managers
    "MessagesManager",
    "ModerationManager",
    "NetworkError",
    "NotFoundError",
    "PermissionError",
    # Permissões e intents
    "Permissions",
    "PresenceStatus",
    "RateLimitError",
    "RequestOptions",
    "RequestTimeoutError",
    # REST
    "RestClient",
    "RestResponse",
    "Role",
    "RoleManagedKind",
    "RolesManager",
    "SelectMenuBuilder",
    "SlashCommandDefinition",
    # Tipos primitivos e menções
    "Snowflake",
    "SquordAPIError",
    # Cliente
    "SquordClient",
    # Erros
    "SquordError",
    "SquordTypeError",
    "TextCommandContext",
    "TextCommandDefinition",
    "Thread",
    "ThreadAutoArchiveMinutes",
    "Transport",
    "UploadStatus",
    "UploadsManager",
    "User",
    "UserFlags",
    "UsersManager",
    "ValidationError",
    "WSClosed",
    "__version__",
    "aiohttp_ws_connector",
    "assert_snowflake",
    "backoff_delay",
    "channel_mention",
    "compare_snowflakes",
    "get_logger",
    "has_any_permission",
    "has_permissions",
    "intents_value",
    "is_valid_snowflake",
    "list_intents",
    "make_api_error",
    "normalize_embed_color",
    "paginate",
    "parse_permissions",
    "permissions_to_string",
    "redact",
    "resolve_channel_permissions",
    "resolve_message_edit_payload",
    "resolve_message_payload",
    "role_mention",
    "route_key_of",
    "safe_allowed_mentions",
    "setup_logging",
    "split_arguments",
    "user_mention",
]
