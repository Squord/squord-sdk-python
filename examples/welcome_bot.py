"""Bot de boas-vindas: cumprimenta quem entra e registra quem sai.

Requer a intent GUILD_MEMBERS (Configurações → Desenvolvedor) e
SEND_MESSAGES no canal do sistema.

export SQUORD_BOT_TOKEN="sqb_..."
python welcome_bot.py
"""

import asyncio
import contextlib
import logging
import os

import squord


async def main() -> None:
    squord.setup_logging(level=logging.INFO)
    client = squord.SquordClient(
        token=os.environ["SQUORD_BOT_TOKEN"],
        graceful_shutdown=True,
    )

    @client.on("ready")
    async def on_ready(event) -> None:
        print(f"Online em {len(event['guilds'])} Space(s).")
        client.set_presence(status="IDLE", custom_status="Dando boas-vindas!")

    @client.on("member.joined")
    async def on_join(data) -> None:
        member: squord.Member = data["member"]
        if member.is_bot:
            return  # não cumprimenta outros bots

        guild_id = data["guildId"]
        guild = await client.guilds.fetch(guild_id)
        system_channel_id = guild.get("systemChannelId")
        if not system_channel_id:
            return

        avatar = member.avatar_url or member.user.avatar_url
        embed = (
            squord.EmbedBuilder()
            .set_title(f"Bem-vindo(a), {member.display_name}!")
            .set_description(
                f"Olá, {squord.user_mention(member.user_id)}! 👋\n\n"
                f"Você é a pessoa número **{guild['memberCount'] + 1}** do Space.\n"
                "Dê uma olhada nas regras e sinta-se em casa."
            )
            .set_color(0x5865F2)
            .set_timestamp()
        )
        if avatar:
            embed.set_thumbnail(avatar)

        await client.messages.send(system_channel_id, {"embeds": [embed]})

    @client.on("member.left")
    async def on_left(data) -> None:
        print(f"{data['userId']} saiu do Space {data['guildId']}.")

    await client.login()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
