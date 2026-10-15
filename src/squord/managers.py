"""Managers REST: os recursos da API encapsulados em métodos previsíveis.

Cada manager chama o ``RestClient`` com os caminhos oficiais e aplica as
regras específicas do recurso (idempotência por ``nonce`` no envio de
mensagens, rotas públicas nas interações, upload de 3 passos, etc.).
"""

from __future__ import annotations

import asyncio
import builtins
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

from .builders import resolve_message_edit_payload, resolve_message_payload
from .http import RequestOptions, TransportRequest
from .types import Snowflake
from .utils import guess_content_type, new_nonce, read_file_bytes

if TYPE_CHECKING:
    from .http import RestClient

MAX_UPLOAD_BYTES = 524_288_000  # teto da API; o limite real vem do plano


class MessagesManager:
    """Enviar, editar, apagar, reagir, fixar e consultar mensagens."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    @overload
    async def fetch(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        raise_not_found: Literal[True] = True,
    ) -> dict[str, Any]: ...

    @overload
    async def fetch(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        raise_not_found: Literal[False],
    ) -> dict[str, Any] | None: ...

    async def fetch(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        raise_not_found: bool = True,
    ) -> dict[str, Any] | None:
        try:
            return await self._rest.get(f"/channels/{channel_id}/messages/{message_id}")
        except Exception:
            if raise_not_found:
                raise
            return None

    async def list(
        self,
        channel_id: Snowflake,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> dict[str, Any]:
        """Lista uma página do histórico (padrão 50, máximo 100)."""
        query = {"limit": limit, "before": before, "after": after}
        return await self._rest.get(
            f"/channels/{channel_id}/messages",
            RequestOptions(query=query),
        )

    async def send(
        self,
        channel_id: Snowflake,
        payload: str | dict[str, Any],
        *,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        """Envia uma mensagem.

        O SDK anexa um ``nonce`` automático (idempotência da plataforma):
        falhas de rede podem ser repetidas pelo cliente REST sem duplicar.
        """
        body = resolve_message_payload(payload)
        body.setdefault("nonce", nonce or new_nonce())
        return await self._rest.post(
            f"/channels/{channel_id}/messages",
            body,
            RequestOptions(retryable=True),  # protegido por nonce
        )

    async def edit(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        payload: str | dict[str, Any],
    ) -> dict[str, Any]:
        """Edita; ``embeds``/``components`` substituem a lista inteira."""
        body = resolve_message_edit_payload(payload)
        return await self._rest.patch(f"/channels/{channel_id}/messages/{message_id}", body)

    async def delete(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        """Apaga (204). A do bot sempre; de outros, com ``MANAGE_MESSAGES``."""
        await self._rest.delete(f"/channels/{channel_id}/messages/{message_id}")

    async def react(self, channel_id: Snowflake, message_id: Snowflake, emoji: str) -> None:
        """Reage (``ADD_REACTIONS``). ``emoji``: caractere ou ``<:nome:id>``."""
        from urllib.parse import quote

        await self._rest.put(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}"
        )

    async def remove_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str
    ) -> None:
        from urllib.parse import quote

        await self._rest.delete(
            f"/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji, safe='')}"
        )

    async def list_reactions(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> builtins.list[dict[str, Any]]:
        return await self._rest.get(f"/channels/{channel_id}/messages/{message_id}/reactions")

    async def pin(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        await self._rest.put(f"/channels/{channel_id}/pins/{message_id}")

    async def unpin(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        await self._rest.delete(f"/channels/{channel_id}/pins/{message_id}")

    async def list_pins(self, channel_id: Snowflake) -> builtins.list[dict[str, Any]]:
        return await self._rest.get(f"/channels/{channel_id}/pins")


class ChannelsManager:
    """Canais e threads: consultar, árvore do Space, criar e listar."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    @overload
    async def fetch(
        self,
        channel_id: Snowflake,
        *,
        raise_not_found: Literal[True] = True,
    ) -> dict[str, Any]: ...

    @overload
    async def fetch(
        self,
        channel_id: Snowflake,
        *,
        raise_not_found: Literal[False],
    ) -> dict[str, Any] | None: ...

    async def fetch(
        self,
        channel_id: Snowflake,
        *,
        raise_not_found: bool = True,
    ) -> dict[str, Any] | None:
        try:
            return await self._rest.get(f"/channels/{channel_id}")
        except Exception:
            if raise_not_found:
                raise
            return None

    async def fetch_tree(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        """Árvore de canais do Space (grupos por categoria)."""
        return await self._rest.get(f"/guilds/{guild_id}/channels")

    async def create_thread(
        self,
        channel_id: Snowflake,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Cria thread em canal de texto/anúncios, ou post em fórum."""
        return await self._rest.post(
            f"/channels/{channel_id}/threads", body, RequestOptions(retryable=False)
        )

    async def create_thread_from_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._rest.post(
            f"/channels/{channel_id}/messages/{message_id}/threads",
            body,
            RequestOptions(retryable=False),
        )

    async def list_threads(
        self,
        channel_id: Snowflake,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        archived: str | None = None,
        tag_id: Snowflake | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "cursor": cursor,
            "limit": limit,
            "archived": archived,
            "tagId": tag_id,
        }
        return await self._rest.get(f"/channels/{channel_id}/threads", RequestOptions(query=query))


class GuildsManager:
    """Spaces (na API, ``guild``)."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def fetch(self, guild_id: Snowflake) -> dict[str, Any]:
        """Busca um Space, com o bloco ``self`` do bot nele."""
        return await self._rest.get(f"/guilds/{guild_id}")


class MembersManager:
    """Membros: consultar, listar, editar, expulsar e cargos."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    @overload
    async def fetch(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        raise_not_found: Literal[True] = True,
    ) -> dict[str, Any]: ...

    @overload
    async def fetch(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        raise_not_found: Literal[False],
    ) -> dict[str, Any] | None: ...

    async def fetch(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        raise_not_found: bool = True,
    ) -> dict[str, Any] | None:
        try:
            return await self._rest.get(f"/guilds/{guild_id}/members/{user_id}")
        except Exception:
            if raise_not_found:
                raise
            return None

    async def list(
        self,
        guild_id: Snowflake,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
        role_id: Snowflake | None = None,
        search: str | None = None,
        channel_id: Snowflake | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "limit": limit,
            "before": before,
            "after": after,
            "roleId": role_id,
            "search": search,
            "channelId": channel_id,
        }
        return await self._rest.get(f"/guilds/{guild_id}/members", RequestOptions(query=query))

    async def edit(
        self, guild_id: Snowflake, user_id: Snowflake, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Edita: apelido, cargos (substituem), timeout, surdez/mudo."""
        return await self._rest.patch(
            f"/guilds/{guild_id}/members/{user_id}", body, RequestOptions(retryable=True)
        )

    async def kick(
        self, guild_id: Snowflake, user_id: Snowflake, reason: str | None = None
    ) -> None:
        body = {"reason": reason} if reason else {}
        await self._rest.request(
            "DELETE", f"/guilds/{guild_id}/members/{user_id}", RequestOptions(body=body)
        )

    async def add_role(self, guild_id: Snowflake, user_id: Snowflake, role_id: Snowflake) -> None:
        await self._rest.put(f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

    async def remove_role(
        self, guild_id: Snowflake, user_id: Snowflake, role_id: Snowflake
    ) -> None:
        await self._rest.delete(f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")


class RolesManager:
    """Cargos de um Space."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def list(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        return await self._rest.get(f"/guilds/{guild_id}/roles")


class ModerationManager:
    """Moderação: banir e desbanir (o que a API expõe a bots hoje)."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def ban(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        reason: str | None = None,
        delete_message_seconds: int = 0,
    ) -> dict[str, Any]:
        """Bane (``BAN_MEMBERS``); até 7 dias de histórico recentes removíveis."""
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        if delete_message_seconds:
            body["deleteMessageSeconds"] = delete_message_seconds
        return await self._rest.put(
            f"/guilds/{guild_id}/bans/{user_id}", body, RequestOptions(retryable=False)
        )

    async def unban(self, guild_id: Snowflake, user_id: Snowflake) -> None:
        """Desbane (``BAN_MEMBERS``). Bans da plataforma não podem ser desfeitos."""
        await self._rest.delete(f"/guilds/{guild_id}/bans/{user_id}")


class UploadsManager:
    """O fluxo oficial de anexos: reserva → ``PUT`` dos bytes → confirmação.

    Anexos não vão no JSON da mensagem. O ``PUT`` dos bytes vai para a URL
    assinada do storage (fora da API do Squord, **sem** o header do bot,
    repetindo os headers do alvo exatamente); a confirmação é idempotente.
    Depois, o ``id`` do upload entra em ``attachmentIds`` (até 10 por
    mensagem; cada upload só entra em uma).
    """

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def reserve(self, body: dict[str, Any]) -> dict[str, Any]:
        """Reserva um upload (``POST /uploads``). Não é idempotente."""
        return await self._rest.post("/uploads", body, RequestOptions(retryable=False))

    async def confirm(
        self, upload_id: Snowflake, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Confirma (``POST /uploads/{id}/confirm``). Idempotente."""
        return await self._rest.post(
            f"/uploads/{upload_id}/confirm", body or {}, RequestOptions(retryable=True)
        )

    async def upload(
        self,
        *,
        guild_id: Snowflake,
        path: str | Path | None = None,
        data: bytes | str | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Fluxo completo: reserva, envia os bytes e confirma (``READY``)."""
        if path is not None:
            path_obj = Path(path)
            if not path_obj.is_file():
                msg = f"Caminho de upload não é um arquivo: {path}"
                raise ValueError(msg)
            bytes_data = await asyncio.to_thread(read_file_bytes, path_obj)
            filename = filename or path_obj.name
        elif data is not None:
            bytes_data = data.encode("utf-8") if isinstance(data, str) else data
            filename = filename or "arquivo"
        else:
            msg = "Informe path ou data para o upload"
            raise ValueError(msg)

        if len(bytes_data) <= 0:
            msg = "O arquivo está vazio (size 0)"
            raise ValueError(msg)
        if len(bytes_data) > MAX_UPLOAD_BYTES:
            msg = f"O arquivo passa de 500 MB ({len(bytes_data)} bytes); o limite real vem do plano"
            raise ValueError(msg)

        reservation = await self._rest.post(
            "/uploads",
            {
                "scope": "attachments",
                "filename": filename,
                "contentType": content_type or guess_content_type(filename),
                "size": len(bytes_data),
                "guildId": guild_id,
            },
            RequestOptions(retryable=False),
        )

        target = reservation.get("target") or {}
        request = TransportRequest(
            method=str(target.get("method") or "PUT"),
            url=str(target["uploadUrl"]),
            headers=dict(target.get("headers") or {}),
            data=bytes_data,
        )
        response = await self._rest.transport.request(request)
        if not 200 <= response.status < 300:
            detail = response.body.decode("utf-8", errors="replace")[:200]
            msg = f"O envio dos bytes falhou (HTTP {response.status}): {detail}"
            raise RuntimeError(msg)

        return await self.confirm(str(reservation["upload"]["id"]))

    async def upload_for_attachment(
        self,
        *,
        guild_id: Snowflake,
        path: str | Path | None = None,
        data: bytes | str | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> Snowflake:
        """Atalho: envia um arquivo e devolve o ``id`` para ``attachmentIds``."""
        upload = await self.upload(
            guild_id=guild_id,
            path=path,
            data=data,
            filename=filename,
            content_type=content_type,
        )
        return str(upload["id"])


class InteractionsManager:
    """Callback da primeira resposta e follow-ups.

    Rotas públicas: o token vai no caminho e **não** se envia
    ``Authorization``. A primeira resposta é a única aceita como callback
    (``409 INTERACTION_ALREADY_ACKNOWLEDGED`` na segunda) e follow-up antes
    da primeira resposta dá ``409 INTERACTION_NOT_ACKNOWLEDGED``.
    """

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def _callback(
        self,
        interaction_id: str,
        token: str,
        body: dict[str, Any],
    ) -> None:
        await self._rest.post(
            f"/interactions/{interaction_id}/{token}/callback",
            body,
            RequestOptions(auth=False, retryable=False),
        )

    async def reply(self, interaction_id: str, token: str, data: dict[str, Any]) -> None:
        """Resposta ``MESSAGE``. Um 409 de "já respondida" é tratado como ok."""
        try:
            await self._callback(interaction_id, token, {"type": "MESSAGE", "data": data})
        except Exception as err:
            if _is_already_acknowledged(err):
                return
            raise

    async def defer(self, interaction_id: str, token: str) -> None:
        """``DEFERRED``: avisa que o bot está processando ("pensando")."""
        try:
            await self._callback(interaction_id, token, {"type": "DEFERRED"})
        except Exception as err:
            if _is_already_acknowledged(err):
                return
            raise

    async def update(self, interaction_id: str, token: str, data: dict[str, Any]) -> None:
        """``UPDATE`` (só componente): edita a mensagem do componente clicado."""
        try:
            await self._callback(interaction_id, token, {"type": "UPDATE", "data": data})
        except Exception as err:
            if _is_already_acknowledged(err):
                return
            raise

    async def acknowledge_component(self, interaction_id: str, token: str) -> None:
        """``DEFERRED_UPDATE`` (só componente): confirma o clique sem mudar nada."""
        try:
            await self._callback(interaction_id, token, {"type": "DEFERRED_UPDATE"})
        except Exception as err:
            if _is_already_acknowledged(err):
                return
            raise

    async def followup(self, interaction_id: str, token: str, data: dict[str, Any]) -> None:
        """Follow-up: mensagem extra depois da primeira resposta (``204``)."""
        await self._rest.post(
            f"/interactions/{interaction_id}/{token}/followups",
            data,
            RequestOptions(auth=False, retryable=False),
        )


def _is_already_acknowledged(err: BaseException) -> bool:
    return (
        isinstance(err, Exception)
        and getattr(err, "status", None) == 409
        and getattr(err, "code", None) == "INTERACTION_ALREADY_ACKNOWLEDGED"
    )


class ApplicationCommandsManager:
    """Comandos de barra (registro em bloco).

    Registrar é uma **sobrescrita** (``PUT``): a lista enviada substitui a
    anterior — comandos fora da lista são apagados; o mesmo nome mantém o
    ``id``. O padrão é registrar a lista inteira na partida do bot.
    """

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def list_global(self) -> list[dict[str, Any]]:
        return await self._rest.get("/bots/@me/commands")

    async def set_global(self, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self._rest.put("/bots/@me/commands", commands)

    async def list_guild(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        return await self._rest.get(f"/bots/@me/guilds/{guild_id}/commands")

    async def set_guild(
        self, guild_id: Snowflake, commands: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return await self._rest.put(f"/bots/@me/guilds/{guild_id}/commands", commands)


class BotManager:
    """O próprio bot (visão do dono) e bots públicos."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def fetch_current(self) -> dict[str, Any]:
        """``GET /bots/@me`` — usado pelo ``login()`` para validar o token."""
        return await self._rest.get("/bots/@me")

    async def fetch(self, bot_id: Snowflake) -> dict[str, Any]:
        return await self._rest.get(f"/bots/{bot_id}")


class UsersManager:
    """Usuários."""

    def __init__(self, rest: RestClient) -> None:
        self._rest = rest

    async def fetch_me(self) -> dict[str, Any]:
        """``GET /users/@me`` (em um bot, os campos privados são padrão)."""
        return await self._rest.get("/users/@me")
