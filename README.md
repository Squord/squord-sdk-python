# squord.py — o SDK oficial do Squord

[![CI](https://github.com/Squord/squord-sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Squord/squord-sdk-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/squord.py.svg?label=squord.py)](https://pypi.org/project/squord.py/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)](./LICENSE)

O SDK para criar bots do [Squord](https://docs.squord.com.br) em Python:
REST tipado e assíncrono, gateway em tempo real com reconexão e resume,
comandos de texto e de barra, botões e menus, uploads, moderação,
permissões e testes — sem você implementar nenhum WebSocket, retry ou
rate limit à mão.

```bash
pip install squord.py
```

```python
import asyncio
import os

import squord


async def main() -> None:
    client = squord.SquordClient(token=os.environ["SQUORD_BOT_TOKEN"])

    @client.on("message.created")
    async def on_message(message: squord.Message) -> None:
        if message.author.is_bot:
            return
        if message.content == "!ping":
            await message.reply("Pong! 🏓")

    await client.login()


asyncio.run(main())
```

> **Pré-requisitos**: Python 3.10+ e um token de bot criado em
> **Configurações → Desenvolvedor** do Squord (instale o bot em um Space).
> Documentação da plataforma: <https://docs.squord.com.br>.

---

## Índice

1. [Começo rápido](#começo-rápido)
2. [Eventos](#eventos)
3. [Comandos](#comandos)
4. [Interações: botões e menus](#interações-botões-e-menus)
5. [Mensagens, embeds e anexos](#mensagens-embeds-e-anexos)
6. [Membros, cargos e moderação](#membros-cargos-e-moderação)
7. [Permissões](#permissões)
8. [Erros, rate limits e retentativas](#erros-rate-limits-e-retentativas)
9. [Gateway: reconexão e resume](#gateway-reconexão-e-resume)
10. [Modo REST-only](#modo-rest-only)
11. [Testando seu bot](#testando-seu-bot)
12. [Observabilidade](#observabilidade)
13. [Publicar versões](#publicar-versões)

---

## Começo rápido

```python
import squord

client = squord.SquordClient(
    token=os.environ["SQUORD_BOT_TOKEN"],
    graceful_shutdown=True,  # encerra no SIGINT/SIGTERM
)

@client.on("ready")
async def on_ready(event) -> None:
    print(f"Conectado como {event['user'].display_name}")
    client.set_presence(status="IDLE", custom_status="Tocando no Lounge")

@client.on("message.created")
async def on_message(message: squord.Message) -> None:
    print(f"{message.author_display_name}: {message.content}")

@client.on("error")
async def on_error(error: Exception) -> None:
    print("erro no handler:", error)

await client.login()
```

O ``login()`` valida o token (``GET /bots/@me``), conecta ao gateway e
emite ``ready``. Tudo depois — heartbeat, reconexão com backoff, resume,
deduplicação — é responsabilidade do SDK.

## Eventos

Os nomes seguem o gateway real do Squord. Eventos com entidades chegam
hidratados (``Message``, ``Member``, ``Channel``, ``Role``, ``Thread``,
``Guild``, ``Interaction``); os demais entregam o payload cru da
documentação.

```python
@client.on("message.created")
async def _(message): ...                     # Message

@client.on("member.joined")
async def _(data): ...                        # {"guildId": ..., "member": Member}

@client.on("interaction.created")
async def _(interaction): ...                  # Interaction
```

Ciclo de vida e diagnóstico: ``ready``, ``resumed``, ``reconnecting``,
``disconnect``, ``error``, ``warn``, ``commandError``, ``raw`` (frame
cru) e ``unknownEvent`` (evento futuro, para compatibilidade sem quebrar).

> **Intents** são configuradas por bot no app do Squord e **não** vão no
> identify — o gateway lê as intents do bot ao conectar. Sem a intent
> privilegiada ``MESSAGE_CONTENT``, o ``content`` chega vazio (exceto
> mensagens do próprio bot e as que o mencionam).

## Comandos

O ``CommandRegistry`` cuida dos três tipos (ele é opcional — você também
pode tratar os eventos na mão):

```python
commands = squord.CommandRegistry(client, prefix="!")

# Texto: prefixo, aliases, aspas, cooldown e middleware.
commands.text(squord.TextCommandDefinition(
    name="banir",
    aliases=["ban"],
    cooldown_ms=5_000,
    execute=banir_execute,
))

# Slash: definidos aqui e sincronizados no login (PUT em bloco).
commands.slash(squord.SlashCommandDefinition(
    name="eco",
    description="Repete o que você disse",
    options=[{"type": "STRING", "name": "texto", "description": "O texto", "required": True}],
    execute=eco_execute,
))

# Componentes: handler por customId (aceita prefixo com `*`).
commands.component(squord.ComponentHandlerDefinition(
    custom_id="confirmar:*",
    execute=confirmar_execute,
))
```

- **Registrar é sobrescrever**: o SDK faz o ``PUT`` da lista completa na
  partida, como a plataforma recomenda (escopo global; por Space, use
  ``scope={"kind": "guild", "guildIds": [...]}`` — útil em dev).
- Respostas de slash: ``interaction.reply(...)``,
  ``reply_ephemeral(...)`` (só a pessoa vê), ``defer()`` + ``followup(...)``
  (padrão para trabalho demorado) e, em componentes, ``update(...)`` /
  ``acknowledge()``.
- Opções tipadas: ``get_string``, ``get_integer``, ``get_boolean``, ``get_id``.

## Interações: botões e menus

```python
row = (
    squord.ActionRowBuilder()
    .add_button(squord.Buttons.primary("Confirmar").set_custom_id("confirmar"))
    .add_button(squord.Buttons.link("Docs").set_url("https://docs.squord.com.br"))
)
menu = (
    squord.SelectMenuBuilder("tema")
    .add_option("Claro", "claro")
    .add_option("Escuro", "escuro", description="O padrão")
)
await channel.send({"content": "Escolha:", "components": [row, squord.ActionRowBuilder().set_select_menu(menu)]})
```

Regras da plataforma, validadas pelo builder: 5 linhas por mensagem, 5
botões por linha ou 1 menu sozinho, ``customId`` único (até 100),
botão de link exige ``https``. Efêmeras só aceitam botões de link.

## Mensagens, embeds e anexos

```python
embed = (
    squord.EmbedBuilder()
    .set_title("Status do servidor")
    .set_description("Todos os serviços operacionais.")
    .set_color(0xF5A623)
    .add_field("API", "Online", inline=True)
    .add_field("Gateway", "Online", inline=True)
    .set_timestamp()
)

await channel.send({"content": "Atualização", "embeds": [embed]})

# Idempotência: cada envio ganha um nonce automático; falhas de rede podem
# ser repetidas com segurança pelo cliente REST sem duplicar a mensagem.
sent = await channel.send("Relatório importante")
await sent.edit("Relatório importante (atualizado)")
await sent.react("👍")
await sent.pin()

# Histórico com paginação por cursor (sem carregar tudo em memória):
async for message in squord.paginate(lambda params: client.messages.list(channel.id, **params)):
    ...  # processa cada mensagem
```

**Uploads** seguem o fluxo oficial de 3 passos (reserva → ``PUT`` dos
bytes → confirmação), abstraído em uma chamada:

```python
upload = await client.uploads.upload(
    guild_id=space_id,       # bots sempre informam o Space
    path="relatorios/daily.pdf",
    filename="relatorio.pdf",
    content_type="application/pdf",
)
await channel.send({"content": "Segue o relatório.", "attachmentIds": [upload["id"]]})
```

## Membros, cargos e moderação

```python
guild = await client.guilds.fetch(space_id)          # Space, com self.permissions
member = await client.members.fetch(space_id, user_id)
page = await client.members.list(space_id, limit=50, role_id=role_id)  # cursor
roles = await client.roles.list(space_id)

await member.add_role(role_id)
await member.set_nickname("Novo apelido")
await member.timeout(datetime.timedelta(minutes=1) + datetime.now(timezone.utc))
await member.kick("motivo")
await client.moderation.ban(space_id, user_id, reason="spam", delete_message_seconds=3600)
await client.moderation.unban(space_id, user_id)
```

A hierarquia é respeitada pelo backend (``HIERARCHY_BLOCKED``,
``ROLE_ABOVE_ACTOR``, ``OWNER_PROTECTED``, ``ROLE_MANAGED`` chegam como
``PermissionError``/``SquordAPIError`` com o ``code`` estável).

## Permissões

Permissões são strings decimais de 64 bits; em Python, ``int`` já tem
precisão arbitrária — use ``squord.Permissions`` (um ``IntFlag``):

```python
from squord import Permissions

bits = Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
str(int(bits))            # "139713" — o formato que vai na API

guild = await client.guilds.fetch(space_id)
if guild.self_permissions & Permissions.BAN_MEMBERS: ...

mine = await client.my_permissions_in(channel_id)     # resolução local com overwrites
can_pin = await client.has_permissions_in(channel_id, Permissions.PIN_MESSAGES)
```

A resolução local é conveniência: **o backend é a autoridade final**.

## Erros, rate limits e retentativas

O cliente REST aplica a política recomendada pela documentação: espera
``details.retryAfter`` no 429 e repete; backoff em 5xx e falhas de rede
**só em operações idempotentes ou com nonce**; repete ``409
COMMANDS_CONFLICT``/``THREAD_CHANGED``; demais 4xx falham na hora;
``RequestTimeoutError`` tipado no timeout. Além do 429 reativo, observa
os headers ``X-RateLimit-*`` e aplica teto global conservador de 45 req/s.

```python
from squord import PermissionError, SquordAPIError

try:
    await channel.send("oi")
except PermissionError as err:
    print("falta a permissão:", err.missing_permission)
except SquordAPIError as err:
    print("code:", err.code, "requestId:", err.request_id)
```

Hierarquia: ``SquordError`` → ``SquordAPIError`` (``status``, ``code``,
``request_id``, ``details``) → ``AuthenticationError``/``InvalidTokenError``,
``PermissionError``, ``NotFoundError``, ``ValidationError`` (``issues``),
``RateLimitError`` (``retry_after``, ``bucket``, ``exhausted_retries``),
``NetworkError``, ``RequestTimeoutError``, ``GatewayError``
(``close_code``, ``reason``).

## Gateway: reconexão e resume

Protocolo completo: ``hello`` → ``identify`` (15 s) → ``ready``; heartbeat
no intervalo anunciado (com jitter no primeiro); ``heartbeat.ack`` com
medida de latência; conexão zumbi detectada e fechada; reconexão com
backoff exponencial e jitter (1 s → 60 s); ``resume`` com replay dos
eventos perdidos; ``invalid_session`` caindo para ``identify`` na mesma
conexão; deduplicação por ``s``; códigos fatais (4004/4013/4014) sem retry.

```python
@client.on("reconnecting")
async def _(info): ...          # {"attempt", "delayMs", "closeCode", "reason"}

@client.on("resumed")
async def _(info): print(info["replayed"], "eventos recuperados")

client.ping_ms                  # latência do último heartbeat
client.gateway.sequence         # última sequência processada
client.reconnect()              # força reconexão (tenta resume)
```

O que o backend não garante, o SDK não inventa: resume vale por 120 s e
replay cobre até 500 eventos; para reconciliar quedas longas, use as
consultas REST.

## Modo REST-only

Para tarefas agendadas, CI e integrações que só publicam:

```python
client = squord.SquordClient(token=token, rest_only=True)
await client.login()                    # valida o token; nenhum WebSocket é aberto
await client.messages.send(channel_id, "deploy concluído ✅")
await client.destroy()
```

## Testando seu bot

O módulo ``squord.testing`` traz um gateway simulado (protocolo real em
memória), um REST em memória e fixtures no formato da documentação:

```python
from squord import SquordClient, Message
from squord.testing import create_mock_environment, fixtures

async def test_ping_bot():
    env = create_mock_environment(heartbeat_interval_ms=100)
    client = SquordClient(token="sqb_1.demo", **env.client_kwargs())

    seen = []
    @client.on("message.created")
    async def _(message: Message):
        seen.append(message.content)
        await message.reply("Pong!")

    await client.login()
    env.gateway.emit_event("message.created", {"message": fixtures.message({"content": "!ping"})})

    assert seen == ["!ping"]
    await client.destroy()
```

Para treinar falhas: ``close_all(4009, ...)`` (resume),
``request_reconnect()`` (frame + 4007), ``refuse_resume_once=True``
(``invalid_session``), ``suppress_heartbeat_ack=True`` (zumbi),
``send_event_with_sequence`` (deduplicação), ``rest.fail_with(...)``
(queda de rede). O ``MockRest`` registra todas as chamadas
(``call_log``/``last_call``) para asserções.

## Observabilidade

O SDK usa o ``logging`` da biblioteca padrão (sem handlers por padrão).
Tokens são **redigidos** (``sqb_...`` e headers viram ``[REDACTED]``) e
conteúdo de mensagens nunca é registrado por conta própria.

```python
squord.setup_logging()                    # ou: logging.basicConfig(level=logging.DEBUG)
client = squord.SquordClient(token=token, log_level=logging.INFO)
```

## Publicar versões

O pacote é publicado no PyPI **automaticamente pelo workflow
[Publicar no PyPI](.github/workflows/publish.yml)** quando um Release do
GitHub é criado — com ruff, mypy, testes, build e *trusted publishing*
(OIDC: nenhum secret no CI).

Configuração única (uma vez, na conta Squord do PyPI): adicione um
*pending trusted publisher* em
<https://pypi.org/manage/account/publishing/> com:

| Campo | Valor |
|---|---|
| PyPI project name | `squord.py` |
| Owner | `Squord` |
| Repository | `squord-sdk-python` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Cortar uma versão: atualize a ``version`` em
[pyproject.toml](./pyproject.toml) e o [CHANGELOG.md](./CHANGELOG.md),
faça o commit, tag `vX.Y.Z` e crie o Release.

---

**Documentação da plataforma**: <https://docs.squord.com.br> ·
**Referência REST (OpenAPI)**: <https://docs.squord.com.br/api> ·
**Protocolo do gateway**: <https://docs.squord.com.br/gateway/visao-geral> ·
**Issues**: <https://github.com/Squord/squord-sdk-python/issues>

MIT © Squord — veja [LICENSE](./LICENSE).
