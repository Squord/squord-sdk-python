"""Bot mínimo do Squord: escuta mensagens e responde !ping.

1. Crie um bot em Configurações → Desenvolvedor (https://docs.squord.com.br)
2. Instale-o em um Space e copie o token.
3. export SQUORD_BOT_TOKEN="sqb_..."
4. python ping_bot.py
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
        graceful_shutdown=True,  # encerra no SIGINT/SIGTERM
    )

    @client.on("ready")
    async def on_ready(event) -> None:
        user = event["user"]
        print(f"Bot conectado: {user.display_name}")
        print(f"Spaces: {', '.join(g['name'] for g in event['guilds']) or 'nenhum'}")

    @client.on("message.created")
    async def on_message(message: squord.Message) -> None:
        if message.author.is_bot:
            return
        if message.content == "!ping":
            started = asyncio.get_event_loop().time()
            await message.reply("Pong! 🏓")
            elapsed_ms = (asyncio.get_event_loop().time() - started) * 1_000
            print(f"Respondido em {elapsed_ms:.0f} ms (gateway: {client.ping_ms} ms)")

    @client.on("error")
    async def on_error(error: Exception) -> None:
        print("Erro no cliente:", error)

    await client.login()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
