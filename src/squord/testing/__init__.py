"""squord.testing — ferramentas para testar bots sem uma comunidade real.

- ``create_mock_rest()``: transporte REST em memória (passe em ``transport=``).
- ``create_mock_gateway()``: gateway simulado que fala o protocolo real
  (passe em ``ws_connector=``).
- ``create_mock_environment()``: REST + gateway já conectados, com a rota
  de login e as rotas comuns respondendo — espalhe
  ``**client_kwargs(env)`` no ``SquordClient`` e pronto.
- ``fixtures``: payloads de exemplo no formato da API.
"""

from __future__ import annotations

from typing import Any

from . import fixtures
from .mock_gateway import MockGatewayServer
from .mock_rest import MockRest, MockRestCall, MockRouteMatch


def create_mock_rest(*, expected_token: str | None = None) -> MockRest:
    """Cria um ``MockRest`` (transporte REST em memória)."""
    return MockRest(expected_token=expected_token)


def create_mock_gateway(
    *,
    heartbeat_interval_ms: int = 30_000,
    token: str | None = None,
    ready: dict[str, Any] | None = None,
    refuse_resume_once: bool = False,
    suppress_heartbeat_ack: bool = False,
) -> MockGatewayServer:
    """Cria um ``MockGatewayServer`` (protocolo real em memória)."""
    return MockGatewayServer(
        heartbeat_interval_ms=heartbeat_interval_ms,
        token=token,
        ready=ready,
        refuse_resume_once=refuse_resume_once,
        suppress_heartbeat_ack=suppress_heartbeat_ack,
    )


class MockEnvironment:
    """Ambiente completo de teste: REST + gateway + opções prontas."""

    def __init__(self, rest: MockRest, gateway: MockGatewayServer) -> None:
        self.rest = rest
        self.gateway = gateway

    def client_kwargs(self, *, reconnect_base_ms: float = 20) -> dict[str, Any]:
        """Argumentos prontos para o ``SquordClient`` (``api_base_url`` e cia.)."""
        return {
            "api_base_url": "https://mock.test",
            "transport": self.rest,
            "ws_connector": self.gateway.ws_connector,
            "reconnect_base_ms": reconnect_base_ms,
        }


def create_mock_environment(
    *,
    heartbeat_interval_ms: int = 200,
    token: str | None = None,
    ready: dict[str, Any] | None = None,
    suppress_heartbeat_ack: bool = False,
) -> MockEnvironment:
    """Monta o ambiente completo: login respondendo, envio de mensagens
    ecoando e sincronização de comandos aceitando — zero setup.

    ```python
    env = create_mock_environment()
    client = SquordClient(token="sqb_1.demo", **env.client_kwargs())

    @client.on("message.created")
    async def on_message(message): ...

    await client.login()
    env.gateway.emit_event("message.created", {"message": fixtures.message()})
    ```
    """
    rest = create_mock_rest()
    rest.get("/bots/@me", lambda match: {"status": 200, "body": fixtures.bot()})
    rest.post(
        "/channels/:channel_id/messages",
        lambda match: {
            "status": 201,
            "body": fixtures.message(
                {
                    "channelId": match.params["channel_id"],
                    "content": (match.body or {}).get("content", ""),
                    "replyToId": (match.body or {}).get("replyToId"),
                    "nonce": (match.body or {}).get("nonce"),
                    "author": fixtures.bot_user(),
                }
            ),
        },
    )
    rest.put("/bots/@me/commands", lambda match: {"status": 200, "body": []})
    rest.put(
        "/bots/@me/guilds/:guild_id/commands",
        lambda match: {"status": 200, "body": []},
    )
    rest.get(
        "/channels/:channel_id",
        lambda match: {"status": 200, "body": fixtures.channel({"id": match.params["channel_id"]})},
    )
    rest.get(
        "/guilds/:guild_id",
        lambda match: {"status": 200, "body": fixtures.guild({"id": match.params["guild_id"]})},
    )

    gateway = create_mock_gateway(
        heartbeat_interval_ms=heartbeat_interval_ms,
        token=token,
        ready=ready,
        suppress_heartbeat_ack=suppress_heartbeat_ack,
    )
    return MockEnvironment(rest, gateway)


__all__ = [
    "MockEnvironment",
    "MockGatewayServer",
    "MockRest",
    "MockRestCall",
    "MockRouteMatch",
    "create_mock_environment",
    "create_mock_gateway",
    "create_mock_rest",
    "fixtures",
]
