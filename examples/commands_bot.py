"""Bot com os dois tipos de comando:

- comandos de texto com prefixo (!ping, !avatar, !banir)
- comandos de barra (/eco, /confirmar), sincronizados no login
- botões e menus com handlers por customId

export SQUORD_BOT_TOKEN="sqb_..."
python commands_bot.py
"""

import asyncio
import contextlib
import logging
import os

import squord

client = squord.SquordClient(
    token=os.environ["SQUORD_BOT_TOKEN"],
    graceful_shutdown=True,
    enable_cache=True,  # cache opcional de Spaces, canais, membros e cargos
)

commands = squord.CommandRegistry(client, prefix="!")


# --------------------------------------------------------------------
# Comandos de texto
# --------------------------------------------------------------------


async def _ping(context: squord.TextCommandContext) -> None:
    await context.reply(f"Pong! Gateway: {client.ping_ms} ms")


commands.text(squord.TextCommandDefinition(name="ping", execute=_ping))


async def _avatar(context: squord.TextCommandContext) -> None:
    message = context.message
    target_id = message.mentioned_user_ids[0] if message.mentioned_user_ids else message.author_id
    member = await client.members.fetch(message.guild_id, target_id) if message.guild_id else None
    display_name = (
        member["nickname"]
        if member and member.get("nickname")
        else ((member or {}).get("user", {}).get("displayName") or message.author_display_name)
    )
    avatar = (
        (member or {}).get("avatarUrl")
        or (member or {}).get("user", {}).get("avatarUrl")
        or message.author.avatar_url
    )
    embed = squord.EmbedBuilder().set_title(f"Avatar de {display_name}").set_color(0xF5A623)
    if avatar:
        embed.set_image(avatar)
    await context.reply({"embeds": [embed]})


commands.text(squord.TextCommandDefinition(name="avatar", execute=_avatar))


async def _banir_before(context: squord.TextCommandContext) -> bool:
    """Verificação local: o backend continua sendo a autoridade final."""
    can_ban = await client.has_permissions_in(
        context.message.channel_id, squord.Permissions.BAN_MEMBERS
    )
    if not can_ban:
        await context.reply("Falta `BAN_MEMBERS` para mim neste canal.")
        return False
    return True


async def _banir(context: squord.TextCommandContext) -> None:
    message = context.message
    target = message.mentioned_user_ids[0] if message.mentioned_user_ids else None
    if not message.guild_id or not target:
        await context.reply("Use assim: `!banir <@pessoa> [motivo]`")
        return
    reason = context.raw_args.replace(f"<@{target}>", "").strip() or "sem motivo"
    await client.moderation.ban(message.guild_id, target, reason=reason)
    await context.reply(f"{squord.user_mention(target)} foi banido. Motivo: {reason}")


commands.text(
    squord.TextCommandDefinition(
        name="banir",
        aliases=["ban"],
        cooldown_ms=5_000,
        before_execute=_banir_before,
        execute=_banir,
    )
)


# --------------------------------------------------------------------
# Comandos de barra (sincronizados com PUT em bloco no login)
# --------------------------------------------------------------------


async def _eco(interaction: squord.Interaction) -> None:
    await interaction.reply(interaction.get_string("texto", required=True))


commands.slash(
    squord.SlashCommandDefinition(
        name="eco",
        description="Repete o que você disse",
        options=[
            {
                "type": "STRING",
                "name": "texto",
                "description": "O texto a repetir",
                "required": True,
            }
        ],
        execute=_eco,
    )
)


async def _confirmar(interaction: squord.Interaction) -> None:
    row = (
        squord.ActionRowBuilder()
        .add_button(squord.Buttons.primary("Confirmar").set_custom_id("confirmar:sim"))
        .add_button(squord.Buttons.secondary("Cancelar").set_custom_id("confirmar:nao"))
        .add_button(squord.Buttons.link("Docs").set_url("https://docs.squord.com.br"))
    )
    await interaction.reply({"content": "Escolha uma opção:", "components": [row]})


commands.slash(
    squord.SlashCommandDefinition(
        name="confirmar",
        description="Mostra botões de exemplo",
        execute=_confirmar,
    )
)


# --------------------------------------------------------------------
# Componentes (customId aceita prefixo com *)
# --------------------------------------------------------------------


async def _on_component(interaction: squord.Interaction) -> None:
    escolha = (interaction.custom_id or "").split(":")[-1]
    # UPDATE edita a própria mensagem do componente.
    await interaction.update({"content": f"Você escolheu: **{escolha}**", "components": []})


commands.component(
    squord.ComponentHandlerDefinition(custom_id="confirmar:*", execute=_on_component)
)


# --------------------------------------------------------------------
# Ciclo de vida
# --------------------------------------------------------------------


@client.on("ready")
async def on_ready(event) -> None:
    print(f"Conectado como {event['user'].username}")


@client.on("member.joined")
async def on_join(data) -> None:
    member: squord.Member = data["member"]
    print(f"{member.display_name} entrou no Space {data['guildId']}")


async def main() -> None:
    squord.setup_logging(level=logging.INFO)
    await client.login()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
