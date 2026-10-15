# Testando seu bot

Como testar bots do Squord sem uma comunidade real — com o subpath
`squord.testing`, que traz um gateway simulado (protocolo real em memória)
e um REST em memória.

## Setup

```python
from squord import SquordClient
from squord.testing import create_mock_environment

def make_client():
    env = create_mock_environment(heartbeat_interval_ms=100)
    client = SquordClient(token="sqb_1.demo", **env.client_kwargs())
    # client_kwargs injeta: api_base_url, transport (REST mock),
    # ws_connector (gateway mock) e reconnect_base_ms curto.
    return client, env
```

> No Python, o ``client_kwargs()`` do ambiente já aponta ``api_base_url``
> para o host do mock — os padrões de rota batem sem esforço.

## Simulando eventos

```python
client, env = make_client()
await client.login()

env.gateway.emit_event("message.created", {"message": fixtures.message({"content": "!ping"})})
env.gateway.emit_event("member.joined", {"guildId": "g", "member": fixtures.member()})
env.gateway.emit_event("interaction.created", fixtures.command_interaction())
```

`fixtures` traz payloads no formato real da documentação: `user`, `botUser`,
`member`, `channel`, `role`, `guild`, `message`, `commandInteraction`,
`componentInteraction`, `command`, `bot` — todos aceitam overrides parciais.

## Treinando falhas do gateway

```python
# Queda com sessão retomável (o SDK faz resume e recupera os eventos):
env.gateway.emit_event("message.created", {"message": fixtures.message()})  # s=1
env.gateway.close_all(4009, "session timeout")
env.gateway.emit_event("message.deleted", {"messageId": "x", "channelId": "c", "guildId": "g"})  # perdido
# → o cliente reconecta, reenvia o perdido e emite "resumed"

# O servidor pedindo reconexão (frame reconnect + fechamento 4007):
env.gateway.request_reconnect("gateway shutting down")

# Resume recusado → invalid_session → identify na mesma conexão:
env2 = create_mock_environment(refuse_resume_once=True)  # gateway kwarg

# Conexão zumbi (sem heartbeat.ack) → o SDK fecha e retoma:
env3 = create_mock_environment(suppress_heartbeat_ack=True)

# Token errado no identify → 4004, sem reconexão:
env4 = create_mock_environment(token="sqb_certo.segredo")
# ( passe um token errado ao SquordClient e o login falha )
```

Opções do ambiente: `heartbeat_interval_ms`, `token`, `ready` (userId/guilds),
`refuse_resume_once`, `suppress_heartbeat_ack`. Diagnóstico do gateway:
`connection_count`, `last_sequence`, `total_events`,
`send_event_with_sequence` (para treinar deduplicação com `s` repetido).

## Asserções no REST

```python
assert len(env.rest.call_log) == 2
last = env.rest.last_call
assert last.path == "/channels/c1/messages"
assert isinstance(last.body["nonce"], str)

# Simulando respostas da API (re-registrar a rota substitui):
env.rest.get("/x", lambda m: {"status": 403, "body": {"code": "MISSING_PERMISSION", "message": "..."}})
env.rest.get("/x", lambda m: {"status": 429, "body": {"code": "RATE_LIMITED",
    "message": "...", "details": {"bucket": "DEFAULT", "retryAfter": 1}}})

# Falha de rede total:
def boom(call):
    raise RuntimeError("fetch failed")
env.rest.fail_with(boom)
```

O mock aplica as validações de protocolo do REST: header `Authorization`
(corrija com `expectedToken`), envelope de erro idêntico ao oficial e
`x-request-id` em toda resposta. Rotas não registradas respondem
`404 NOT_FOUND` — se seu teste pedir uma rota que não existe no Squord,
o erro aparece na hora.

## Testando handlers isoladamente

```python
import asyncio
import squord
from squord.testing import create_mock_environment, fixtures

async def test_comando_de_texto_responde_com_args_certos():
    env = create_mock_environment()
    client = squord.SquordClient(token="sqb_1.demo", **env.client_kwargs())
    commands = squord.CommandRegistry(client, prefix="!", sync_on_login=False)
    vistos = []
    commands.text(squord.TextCommandDefinition(
        name="eco", execute=lambda ctx: vistos.append(ctx.args)
    ))
    await client.login()

    env.gateway.emit_event("message.created", {
        "message": fixtures.message({"content": '!eco "arg com espaço" fim'})
    })
    await asyncio.sleep(0.1)
    assert vistos == [["arg com espaço", "fim"]]
    await client.destroy()
```

Como o ``CommandRegistry`` escuta os mesmos eventos do cliente, os testes de
comandos, componentes e mensagens rodam pelo mesmo caminho de produção —
só a rede é falsa. Com ``pytest-asyncio`` em modo ``auto``, os testes
assíncronos nem precisam de marcador.

## O que os próprios testes do SDK cobrem

A suíte do pacote (90 testes) exercita exatamente esses fluxos e serve de
receita: `packages/sdk/test/unit` (builders, parser, cache, permissões,
intents, backoff, política de retries do REST, rate limits locais) e
`packages/sdk/test/integration` (login, eventos hidratados, respostas com
nonce, interações, comandos com cooldown, upload completo, resume,
invalid_session, zumbi, reconnect do servidor).
