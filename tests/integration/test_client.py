"""Integração: SquordClient com login, eventos, comandos e interações."""

import asyncio

import pytest

import squord
from squord import CommandRegistry, SquordClient
from squord.errors import SquordAPIError, SquordTypeError
from squord.testing import create_mock_environment, fixtures

TOKEN = "sqb_1300000000000000010.demo"


def make_client(**overrides) -> tuple[SquordClient, object]:
    env = create_mock_environment(heartbeat_interval_ms=200)
    kwargs = {"token": TOKEN, **env.client_kwargs()}
    kwargs.update(overrides)
    client = SquordClient(**kwargs)
    return client, env


class TestLogin:
    async def test_recusa_token_malformado_sem_requisicao(self):
        with pytest.raises(SquordTypeError, match="sqb_"):
            SquordClient(token="nao-e--um-token")
        with pytest.raises(SquordTypeError):
            SquordClient(token="")

    async def test_login_valida_token_e_emite_ready(self):
        client, _ = make_client()
        ready_events = []
        client.on("ready", lambda event: ready_events.append(event))
        await client.login()

        assert len(ready_events) == 1
        event = ready_events[0]
        assert event["user"].username == "bot~meubot"
        assert event["user"].is_bot is True
        assert client.user_id == "1300000000000000010"
        assert client.is_ready()
        await client.destroy()

    async def test_login_propaga_erro_de_token(self):
        env = create_mock_environment()
        env.rest.get(
            "/bots/@me",
            lambda m: {
                "status": 401,
                "body": {"code": "INVALID_TOKEN", "message": "Invalid token"},
            },
        )
        client = SquordClient(token=TOKEN, **env.client_kwargs())
        with pytest.raises(SquordAPIError) as info:
            await client.login()
        assert info.value.status == 401

    async def test_rest_only_nao_abre_gateway(self):
        env = create_mock_environment()
        client = SquordClient(token=TOKEN, rest_only=True, **env.client_kwargs())
        ready = []
        client.on("ready", lambda event: ready.append(event))
        await client.login()
        assert len(ready) == 1
        assert env.gateway.connection_count == 0
        # Manager REST continua utilizável
        env.rest.get("/channels/:id", lambda m: {"status": 200, "body": fixtures.channel()})
        channel = await client.channels.fetch("1300000000000000040")
        assert channel["name"] == "geral"
        await client.destroy()


class TestEventos:
    async def test_message_created_hidratado_e_resposta_com_nonce(self):
        client, env = make_client()
        received = asyncio.Event()
        message_holder = {}

        async def on_message(message: squord.Message) -> None:
            message_holder["message"] = message
            received.set()

        client.on("message.created", on_message)
        await client.login()

        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!ping"})}
        )
        await asyncio.wait_for(received.wait(), timeout=2)
        message = message_holder["message"]
        assert message.content == "!ping"
        assert message.author.username == "ana"
        assert message.author_display_name == "Ana"
        assert message.channel_id == "1300000000000000040"

        reply = await message.reply("Pong! 🏓")
        assert reply.content == "Pong! 🏓"  # o mock ecoa o conteúdo enviado
        last = env.rest.last_call
        assert last.body["replyToId"] == message.id
        assert isinstance(last.body["nonce"], str)  # idempotência automática
        assert last.body["allowedMentions"] == {"users": True, "roles": False, "everyone": False}
        await client.destroy()

    async def test_message_deleted_payload_cru(self):
        client, env = make_client()
        received = asyncio.Event()
        holder = {}

        async def on_deleted(payload) -> None:
            holder["payload"] = payload
            received.set()

        client.on("message.deleted", on_deleted)
        await client.login()

        env.gateway.emit_event(
            "message.deleted",
            {
                "messageId": "1300000000000000100",
                "channelId": "1300000000000000040",
                "guildId": "1300000000000000001",
            },
        )
        await asyncio.wait_for(received.wait(), timeout=2)
        assert holder["payload"]["messageId"] == "1300000000000000100"
        await client.destroy()

    async def test_evento_desconhecido_chega_em_unknown_event(self):
        client, env = make_client()
        received = asyncio.Event()
        holder = {}

        async def on_unknown(event) -> None:
            holder["event"] = event
            received.set()

        client.on("unknownEvent", on_unknown)
        await client.login()

        env.gateway.emit_event("feature.nova.do.futuro", {"foo": True})
        await asyncio.wait_for(received.wait(), timeout=2)
        assert holder["event"]["type"] == "feature.nova.do.futuro"
        await client.destroy()

    async def test_erro_de_handler_assincrono_nao_derruba(self):
        client, env = make_client()
        errored = asyncio.Event()
        holder = {}

        async def on_error(error: Exception) -> None:
            holder["error"] = error
            errored.set()

        async def boom(message) -> None:
            raise RuntimeError("boom no handler")

        client.on("error", on_error)
        client.on("message.created", boom)
        await client.login()

        env.gateway.emit_event("message.created", {"message": fixtures.message()})
        await asyncio.wait_for(errored.wait(), timeout=2)
        assert "boom" in str(holder["error"])
        assert client.is_ready()
        await client.destroy()

    async def test_member_joined_hidratado(self):
        client, env = make_client()
        received = asyncio.Event()
        holder = {}

        async def on_join(data) -> None:
            holder["data"] = data
            received.set()

        client.on("member.joined", on_join)
        await client.login()

        env.gateway.emit_event(
            "member.joined", {"guildId": "1300000000000000001", "member": fixtures.member()}
        )
        await asyncio.wait_for(received.wait(), timeout=2)
        member: squord.Member = holder["data"]["member"]
        assert member.user.username == "ana"
        assert member.guild_id == "1300000000000000001"
        await client.destroy()


class TestInteracoes:
    async def test_comando_e_componente_com_helpers_tipados(self):
        client, env = make_client()
        seen_command = asyncio.Event()
        seen_component = asyncio.Event()
        holders = {"command": {}, "component": {}}

        commands = CommandRegistry(client, sync_on_login=False)
        env.rest.put(
            "/bots/@me/commands",
            lambda m: {"status": 200, "body": []},
        )

        async def on_command(interaction: squord.Interaction) -> None:
            holders["command"] = interaction
            seen_command.set()

        async def on_component(interaction: squord.Interaction) -> None:
            holders["component"] = interaction
            seen_component.set()

        commands.slash(
            squord.SlashCommandDefinition(
                name="eco",
                description="Repete",
                options=[{"type": "STRING", "name": "texto", "description": "O texto"}],
                execute=on_command,
            )
        )
        commands.component(
            squord.ComponentHandlerDefinition(custom_id="confirmar", execute=on_component)
        )

        env.rest.on(
            "POST",
            "/interactions/:id/:token/callback",
            lambda m: {"status": 204},
        )

        await client.login()

        env.gateway.emit_event(
            "interaction.created",
            fixtures.command_interaction(
                {
                    "command": {
                        "id": "500",
                        "name": "eco",
                        "options": [{"name": "texto", "type": "STRING", "value": "olá"}],
                    }
                }
            ),
        )
        await asyncio.wait_for(seen_command.wait(), timeout=2)
        interaction: squord.Interaction = holders["command"]
        assert interaction.is_command
        assert interaction.get_string("texto") == "olá"

        await interaction.reply("eco!", ephemeral=True)
        last = env.rest.last_call
        assert last.body["type"] == "MESSAGE"
        assert last.body["data"]["ephemeral"] is True
        assert "Authorization" not in last.headers  # rota pública

        env.gateway.emit_event("interaction.created", fixtures.component_interaction())
        await asyncio.wait_for(seen_component.wait(), timeout=2)
        component: squord.Interaction = holders["component"]
        assert component.is_component
        assert component.custom_id == "confirmar"
        assert component.values == []
        await client.destroy()


class TestComandosDeTexto:
    async def test_prefixo_alias_aspas_e_cooldown(self):
        client, env = make_client()
        calls = []
        commands = CommandRegistry(client, prefix="!")

        async def execute(context: squord.TextCommandContext) -> None:
            calls.append({"args": context.args, "raw": context.raw_args})
            await context.reply("ok")

        commands.text(
            squord.TextCommandDefinition(
                name="ban", aliases=["b"], cooldown_ms=60_000, execute=execute
            )
        )
        await client.login()

        # Alias + aspas
        env.gateway.emit_event(
            "message.created",
            {"message": fixtures.message({"content": '!b @ana "spam reincidente" 7d'})},
        )
        await asyncio.sleep(0.15)
        assert len(calls) == 1
        assert calls[0]["args"] == ["@ana", "spam reincidente", "7d"]

        # Cooldown bloqueia a segunda imediata
        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!ban @bob"})}
        )
        await asyncio.sleep(0.15)
        assert len(calls) == 1

        # Sem prefixo não invoca
        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "ban x"})}
        )
        await asyncio.sleep(0.1)
        assert len(calls) == 1

        # Comando desconhecido não invoca
        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!desconhecido"})}
        )
        await asyncio.sleep(0.1)
        assert len(calls) == 1

        # Depois do cooldown limpo, invoca de novo
        commands.clear_cooldowns()
        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!ban @bob"})}
        )
        await asyncio.sleep(0.15)
        assert len(calls) == 2
        await client.destroy()

    async def test_ignora_mensagens_de_bots_por_padrao(self):
        client, env = make_client()
        calls = []
        commands = CommandRegistry(client)

        def execute(context: squord.TextCommandContext) -> None:
            calls.append(context.message.content)

        commands.text(squord.TextCommandDefinition(name="ping", execute=execute))
        await client.login()

        other_bot = fixtures.message(
            {
                "content": "!ping",
                "author": fixtures.bot_user({"id": "999", "username": "bot~outro"}),
            }
        )
        env.gateway.emit_event("message.created", {"message": other_bot})
        await asyncio.sleep(0.1)
        assert calls == []

        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!ping"})}
        )
        await asyncio.sleep(0.15)
        assert calls == ["!ping"]
        await client.destroy()

    async def test_erro_no_handler_vai_para_command_error(self):
        client, env = make_client()
        commands = CommandRegistry(client, sync_on_login=False)
        errored = asyncio.Event()
        holder = {}

        async def on_command_error(context) -> None:
            holder["error"] = context["error"]
            errored.set()

        client.on("commandError", on_command_error)

        async def explode(context: squord.TextCommandContext) -> None:
            raise RuntimeError("boom comando")

        commands.text(squord.TextCommandDefinition(name="boom", execute=explode))
        await client.login()

        env.gateway.emit_event(
            "message.created", {"message": fixtures.message({"content": "!boom"})}
        )
        await asyncio.wait_for(errored.wait(), timeout=2)
        assert "boom comando" in str(holder["error"])
        await client.destroy()


class TestDestroy:
    async def test_destroy_fecha_gateway_e_limpa_listeners(self):
        client, env = make_client()
        await client.login()
        assert env.gateway.connection_count == 1
        await client.destroy()
        assert env.gateway.connection_count == 0
        assert not client.is_ready()
