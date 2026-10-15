"""Registro de comandos: texto (prefixo), slash (comandos de aplicação) e componentes.

- **Texto**: o SDK ouve ``message.created``, faz o parse do prefixo e dos
  argumentos (aspas tratadas) e chama o handler. Suporta aliases,
  cooldowns e middleware ``before_execute``.
- **Slash**: handlers para ``interaction.created`` de comandos. O registro
  pode sincronizar as definições com o Squord (``PUT`` em bloco) na
  partida do bot — registrar é sobrescrever, então a lista deve ser a
  mesma sempre.
- **Componentes**: handlers para cliques em botões e escolhas em menus,
  identificados pelo ``customId`` (aceita prefixo com ``*`` no final).
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .errors import SquordTypeError
from .models import Interaction, Message
from .types import Snowflake
from .utils import split_arguments

if TYPE_CHECKING:
    from .client import SquordClient

_COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


@dataclass(slots=True)
class TextCommandContext:
    """Contexto passado ao handler de um comando de texto."""

    client: SquordClient
    message: Message
    #: Nome invocado (pode ser um alias).
    name: str
    #: Definição do comando registrado.
    command: TextCommandDefinition
    #: Argumentos crus, já com aspas tratadas.
    args: list[str] = field(default_factory=list)
    #: A linha de argumentos como veio (sem o nome do comando).
    raw_args: str = ""

    async def reply(self, payload: str | dict[str, Any]) -> Message:
        """Responde no canal (sem citar)."""
        return await self.message.reply(payload)

    async def reply_with_mention(self, payload: str | dict[str, Any]) -> Message:
        """Responde citando a mensagem original."""
        mention = f"<@{self.message.author_id}>"
        if isinstance(payload, str):
            return await self.message.reply(f"{mention} {payload}")
        body = dict(payload)
        content = body.get("content")
        body["content"] = f"{mention} {content}" if content else f"{mention}"
        return await self.message.reply(body)

    async def react(self, emoji: str) -> None:
        """Reage à mensagem que invocou o comando."""
        await self.message.react(emoji)


@dataclass(slots=True)
class TextCommandDefinition:
    name: str
    execute: Callable[[TextCommandContext], Awaitable[None] | None]
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    hidden: bool = False
    cooldown_ms: float = 0
    ignore_bots: bool | None = None
    guild_ids: list[Snowflake] | None = None
    before_execute: Callable[[TextCommandContext], bool | Awaitable[bool]] | None = None


@dataclass(slots=True)
class SlashCommandDefinition:
    name: str
    description: str
    execute: Callable[[Interaction], Awaitable[None] | None]
    options: list[dict[str, Any]] = field(default_factory=list)
    #: Onde publicar: ``global`` (padrão) ou Spaces específicos.
    scope: dict[str, Any] = field(default_factory=lambda: {"kind": "global"})


@dataclass(slots=True)
class ComponentHandlerDefinition:
    custom_id: str
    #: Terminando em ``*``, casa por prefixo.
    execute: Callable[[Interaction], Awaitable[None] | None]


class CommandRegistry:
    """Registro dos três tipos de comando, anexado a um ``SquordClient``."""

    def __init__(
        self,
        client: SquordClient,
        *,
        prefix: str | Callable[[Message], str | None] = "!",
        sync_on_login: bool = True,
        ignore_bots: bool = True,
        on_error: Callable[[BaseException, dict[str, Any]], None] | None = None,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._sync_on_login = sync_on_login
        self._ignore_bots_default = ignore_bots
        self._on_error = on_error
        self._text: dict[str, TextCommandDefinition] = {}
        self._slash: dict[str, SlashCommandDefinition] = {}
        self._components: dict[str, ComponentHandlerDefinition] = {}
        self._cooldowns: dict[str, float] = {}
        self._attached = False

    # ------------------------------------------------------------- --
    # Registro
    # ------------------------------------------------------------------

    def text(
        self,
        definition: TextCommandDefinition | None = None,
        **kwargs: Any,
    ) -> CommandRegistry:
        """Registra um comando de texto (ou via argumentos nomeados)."""
        command = definition or TextCommandDefinition(**kwargs)
        if not command.name or not isinstance(command.name, str):
            msg = "Comando de texto precisa de name"
            raise SquordTypeError(msg)
        if not callable(command.execute):
            msg = f"Comando {command.name} precisa de execute()"
            raise SquordTypeError(msg)
        for name in [command.name, *command.aliases]:
            key = name.lower()
            if key in self._text:
                msg = f"Comando de texto duplicado: {name}"
                raise SquordTypeError(msg)
            self._text[key] = command
        self._ensure_attached()
        return self

    def slash(
        self,
        definition: SlashCommandDefinition | None = None,
        **kwargs: Any,
    ) -> CommandRegistry:
        """Registra um comando slash (ou via argumentos nomeados)."""
        command = definition or SlashCommandDefinition(**kwargs)
        if not _COMMAND_NAME_RE.match(command.name):
            msg = (
                f"Nome de comando inválido: {command.name} "
                "(use letras minúsculas, números, _ e -, até 32 caracteres)"
            )
            raise SquordTypeError(msg)
        if command.name in self._slash:
            msg = f"Comando slash duplicado: {command.name}"
            raise SquordTypeError(msg)
        self._slash[command.name] = command
        self._ensure_attached()
        return self

    def component(
        self,
        definition: ComponentHandlerDefinition | None = None,
        **kwargs: Any,
    ) -> CommandRegistry:
        """Registra um handler de componente (botão ou menu)."""
        handler = definition or ComponentHandlerDefinition(**kwargs)
        if not handler.custom_id:
            msg = "customId é obrigatório"
            raise SquordTypeError(msg)
        if handler.custom_id in self._components:
            msg = f"Handler de componente duplicado: {handler.custom_id}"
            raise SquordTypeError(msg)
        self._components[handler.custom_id] = handler
        self._ensure_attached()
        return self

    def remove_component(self, custom_id: str) -> CommandRegistry:
        self._components.pop(custom_id, None)
        return self

    def clear_cooldowns(self) -> CommandRegistry:
        self._cooldowns.clear()
        return self

    # ------------------------------------------------------------- --
    # Sincronização de slash commands
    # ------------------------------------------------------------------

    def to_commands_input(self) -> list[dict[str, Any]]:
        """Definições prontas para o ``PUT`` em bloco."""
        return [
            {"name": command.name, "description": command.description, "options": command.options}
            for command in self._slash.values()
        ]

    async def sync(self) -> None:
        """Sobrescreve os comandos de cada escopo (``PUT`` em bloco)."""
        global_commands: list[dict[str, Any]] = []
        guild_scopes: dict[Snowflake, list[dict[str, Any]]] = {}

        for command in self._slash.values():
            entry: dict[str, Any] = {
                "name": command.name,
                "description": command.description,
                "options": command.options,
            }
            scope = command.scope or {"kind": "global"}
            if scope.get("kind") == "global":
                global_commands.append(entry)
            else:
                for guild_id in scope.get("guildIds", []):
                    guild_scopes.setdefault(guild_id, []).append(entry)

        if global_commands:
            await self._client.commands.set_global(global_commands)
        for guild_id, commands in guild_scopes.items():
            await self._client.commands.set_guild(guild_id, commands)

    # ------------------------------------------------------------- --
    # Despacho (público: também usado direto nos testes)
    # ------------------------------------------------------------------

    async def handle_text_message(self, message: Message) -> bool:
        """Processa uma mensagem como possível comando. ``True`` se invocou."""
        prefix = self._resolve_prefix(message)
        if prefix is None or not message.content.startswith(prefix):
            return False

        line = message.content[len(prefix) :].strip()
        if not line:
            return False

        space_index = next((i for i, ch in enumerate(line) if ch.isspace()), None)
        invoked = (line if space_index is None else line[:space_index]).lower()
        raw_args = "" if space_index is None else line[space_index:].strip()

        command = self._text.get(invoked)
        if command is None:
            return False

        if command.guild_ids and message.guild_id not in command.guild_ids:
            return False
        ignore_bots = (
            command.ignore_bots if command.ignore_bots is not None else self._ignore_bots_default
        )
        if ignore_bots and message.author.is_bot:
            return False

        if command.cooldown_ms and command.cooldown_ms > 0:
            key = f"{message.author_id}:{command.name}"
            until = self._cooldowns.get(key, 0)
            now = time.monotonic()
            if until > now:
                return False
            self._cooldowns[key] = now + command.cooldown_ms / 1_000

        context = TextCommandContext(
            client=self._client,
            message=message,
            name=invoked,
            command=command,
            args=split_arguments(raw_args),
            raw_args=raw_args,
        )
        try:
            if command.before_execute is not None:
                allowed = command.before_execute(context)
                if isinstance(allowed, Awaitable):
                    allowed = await allowed
                if allowed is False:
                    return False
            result = command.execute(context)
            if isinstance(result, Awaitable):
                await result
        except Exception as err:
            await self._report_error(err, command=command.name, message=message)
        return True

    async def handle_interaction(self, interaction: Interaction) -> bool:
        """Processa uma interação (slash ou componente). ``True`` se invocou."""
        try:
            if interaction.is_command:
                command_name = str((interaction.command or {}).get("name", ""))
                command = self._slash.get(command_name)
                if command is None:
                    return False
                result = command.execute(interaction)
                if isinstance(result, Awaitable):
                    await result
                return True
            if interaction.is_component:
                handler = self._match_component(interaction.custom_id or "")
                if handler is None:
                    return False
                result = handler.execute(interaction)
                if isinstance(result, Awaitable):
                    await result
                return True
        except Exception as err:
            await self._report_error(err, interaction=interaction)
        return False

    def _match_component(self, custom_id: str) -> ComponentHandlerDefinition | None:
        exact = self._components.get(custom_id)
        if exact is not None:
            return exact
        for pattern, handler in self._components.items():
            if pattern.endswith("*") and custom_id.startswith(pattern[:-1]):
                return handler
        return None

    def _resolve_prefix(self, message: Message) -> str | None:
        if callable(self._prefix):
            return self._prefix(message)
        return self._prefix

    async def _report_error(
        self,
        error: BaseException,
        *,
        command: str | None = None,
        message: Message | None = None,
        interaction: Interaction | None = None,
    ) -> None:
        context = {
            "error": error,
            "command": command,
            "message": message,
            "interaction": interaction,
        }
        if self._on_error is not None:
            self._on_error(error, context)
            return
        await self._client.events.emit("commandError", context)

    def _ensure_attached(self) -> None:
        if self._attached:
            return
        self._attached = True
        self._client.on("message.created", _make_text_dispatcher(self))
        self._client.on("interaction.created", _make_interaction_dispatcher(self))
        if self._sync_on_login:
            if self._client.is_ready():
                _spawn(self._sync_safe())
            else:
                self._client.once("ready", _make_sync_dispatcher(self))

    async def _sync_safe(self) -> None:
        try:
            await self.sync()
        except Exception as err:
            await self._report_error(err)


_BACKGROUND_TASKS: set[Any] = set()


def _spawn(coro: Any) -> None:
    """Agenda uma corrotina em background (erros vão para ``commandError``)."""
    import asyncio

    task = asyncio.get_running_loop().create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _make_text_dispatcher(registry: CommandRegistry) -> Callable[..., Any]:
    async def handler(message: Message) -> None:
        await registry.handle_text_message(message)

    return handler


def _make_interaction_dispatcher(registry: CommandRegistry) -> Callable[..., Any]:
    async def handler(interaction: Interaction) -> None:
        await registry.handle_interaction(interaction)

    return handler


def _make_sync_dispatcher(registry: CommandRegistry) -> Callable[..., Any]:
    async def handler(_: Any) -> None:
        await registry._sync_safe()

    return handler


def inspect_awaitable(value: Any) -> bool:
    """``True`` se o valor é aguardável (handler assíncrono)."""
    import inspect

    return inspect.isawaitable(value)


def _dispatch_text(registry: CommandRegistry) -> Callable[[Message], Any]:
    def handler(message: Message) -> Any:
        return registry.handle_text_message(message)

    return handler


def _dispatch_interaction(registry: CommandRegistry) -> Callable[[Interaction], Any]:
    def handler(interaction: Interaction) -> Any:
        return registry.handle_interaction(interaction)

    return handler


def _dispatch_sync(registry: CommandRegistry) -> Callable[[Any], Any]:
    def handler(_: Any) -> Any:
        asyncio_task(registry._sync_safe())
        return None

    return handler


def asyncio_task(coro: Any) -> None:
    """Agenda uma corrotina em background, guardando referência contra GC.

    A corrotina passada deve tratar os próprios erros (veja ``_sync_safe``).
    """
    import asyncio

    try:
        task = asyncio.get_running_loop().create_task(coro)
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
    except RuntimeError:  # pragma: no cover — sem loop (uso síncrono raro)
        coro.close()
