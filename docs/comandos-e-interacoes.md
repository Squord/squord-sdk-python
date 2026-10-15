# Comandos e interações

Como usar o `CommandRegistry` para os três tipos de comando suportados pelo
Squord: texto com prefixo, comandos de barra e componentes (botões e menus).

## Comandos de texto

São processados pelo SDK a partir de `message.created`. Requerem a intent
`GUILD_MESSAGES`; o **conteúdo** só chega com a intent privilegiada
`MESSAGE_CONTENT` (exceto mensagens do próprio bot e as que o mencionam).

```python
async def _before(context: squord.TextCommandContext) -> bool:
    pode = await client.has_permissions_in(
        context.message.channel_id, squord.Permissions.TIMEOUT_MEMBERS
    )
    if not pode:
        await context.reply("Falta `TIMEOUT_MEMBERS` para mim aqui.")
        return False
    return True

async def _timeout(context: squord.TextCommandContext) -> None:
    target, minutos = context.args[0], context.args[1]  # aspas já tratadas
    member = await client.members.fetch(context.message.guild_id, target)
    await squord.Member(client, member).timeout(
        datetime.now(timezone.utc) + timedelta(minutes=int(minutos))
    )
    await context.reply_with_mention(f"silenciado por {minutos} min.")

commands.text(squord.TextCommandDefinition(
    name="timeout",
    aliases=["silenciar"],
    cooldown_ms=3_000,
    before_execute=_before,
    execute=_timeout,
))
```

O parse: o prefixo (string ou função por mensagem) é removido, o primeiro
token vira o nome (case-insensitive, aliases incluídos) e o resto vira
`context.args` — aspas simples e duplas agrupam argumentos com espaços
(`!banir @ana "spam reincidente" 7d` → 3 argumentos).

Cooldown é por usuário+comando. Mensagens de bots são ignoradas por padrão
(`ignoreBots` no registro).

## Comandos de barra

São comandos de aplicação: registrados no Squord e invocados com `/`.
O bot precisa de sessão aberta no gateway — sem isso, quem invoca recebe
`409 BOT_OFFLINE`.

**Registrar é sobrescrever.** O `PUT` envia a lista completa do escopo e o
Squord substitui a anterior (comandos fora da lista somem; o mesmo nome mantém
o `id`). O padrão é registrar a lista inteira **na partida do bot** — o
`CommandRegistry` faz isso automaticamente no `ready` (`syncOnLogin`).

```python
async def _novidades(interaction: squord.Interaction) -> None:
    completo = interaction.get_boolean("completo") or False
    await interaction.reply("Tudo..." if completo else "Resumo...")

commands.slash(squord.SlashCommandDefinition(
    name="novidades",
    description="Mostra as últimas novidades",
    options=[
        {"type": "BOOLEAN", "name": "completo", "description": "Lista completa"},
        {
            "type": "STRING",
            "name": "tema",
            "description": "Filtrar por tema",
            "choices": [{"name": "Voz", "value": "voz"}, {"name": "Bots", "value": "bots"}],
        },
    ],
    # escopo global por padrão; em desenvolvimento, prefira um Space:
    # scope={"kind": "guild", "guildIds": [space_de_dev]},
    execute=_novidades,
))
```

Limites da plataforma (validados pelo SDK): 100 comandos por escopo, nome até
32 caracteres (`[a-z0-9_-]`), descrição 100, 25 opções por comando, 25 `choices`
por opção (só `STRING` e `INTEGER` têm choices), tipos `STRING`, `INTEGER`,
`BOOLEAN`, `USER`, `CHANNEL`, `ROLE` (estes três últimos chegam como **id**).
O limite de sobrescritas é `COMMANDS_UPDATE`: 10 por minuto.

Ao invocar, o Squord já validou tudo (canal visível, opções corretas, ids do
Space) — o `interaction.created` chega com `command.options` prontos, tipados
por `getString/getInteger/getBoolean/getId`.

## Responder interações

A primeira resposta é a única aceita como callback; a janela total é de
**15 minutos**, e o limite é 5 respostas (callback + follow-ups) por 5 s.

| Método | Tipo | Serve para |
|---|---|---|
| Método | Tipo | Serve para |
|---|---|---|
| `interaction.reply(payload)` | `MESSAGE` | postar a resposta (com marca de comando) |
| `interaction.reply_ephemeral(payload)` | `MESSAGE` + `ephemeral` | só quem invocou vê; não é salva; só botões de link |
| `interaction.defer()` | `DEFERRED` | "bot pensando"; resultado vem depois, por follow-up |
| `interaction.update(payload)` | `UPDATE` | componente: edita a mensagem clicada |
| `interaction.acknowledge()` | `DEFERRED_UPDATE` | componente: confirma o clique sem mudar nada |
| `interaction.followup(payload)` | — | mensagem extra depois da primeira resposta |

O padrão para trabalho demorado: `defer()` logo (o app avisa "não respondeu"
após ~10 s) e `followup()` quando terminar.

## Componentes

```python
row = (
    squord.ActionRowBuilder()
    .add_button(squord.Buttons.primary("Confirmar").set_custom_id("confirmar"))
    .add_button(squord.Buttons.danger("Excluir").set_custom_id("excluir"))
    .add_button(squord.Buttons.link("Abrir").set_url("https://..."))
)

async def _excluir(interaction: squord.Interaction) -> None:
    # Confira o user e as permissões para ações sensíveis: o customId é
    # só um texto seu, não uma autorização.
    await interaction.update({"content": "Excluído.", "components": []})

commands.component(
    squord.ComponentHandlerDefinition(custom_id="excluir", execute=_excluir)
    # ou custom_id="acao:*" para casar por prefixo
)
```

Regras da plataforma (o builder valida antes de enviar): até 5 linhas por
mensagem; cada linha tem 1–5 botões **ou** exatamente 1 menu; `customId` único
na mensagem (até 100 caracteres); botão de link tem `url` e não gera interação;
menus têm 1–25 opções, `minValues`/`maxValues` padrão 1.

O clique chega em `interaction.created` com `type: "COMPONENT"`, o `customId`,
os `values` do menu (vazio em botão) e o `messageId` — use
`interaction.fetchComponentMessage()` para ler a mensagem origem quando precisar.
