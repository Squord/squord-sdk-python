"""Relatórios agendados sem gateway: só o cliente REST.

Ideal para cron, CI e integrações que só publicam mensagens. Nenhuma
conexão WebSocket é aberta (rest_only=True).

export SQUORD_BOT_TOKEN="sqb_..."
export SQUORD_CHANNEL_ID="1300000000000000040"
export SQUORD_GUILD_ID="1300000000000000001"
python scheduled_reports.py
"""

import asyncio
import logging
import os

import squord


async def main() -> None:
    squord.setup_logging(level=logging.INFO)

    client = squord.SquordClient(
        token=os.environ["SQUORD_BOT_TOKEN"],
        rest_only=True,  # valida o token e resolve; gateway não é aberto
    )
    await client.login()

    channel_id = os.environ["SQUORD_CHANNEL_ID"]
    guild_id = os.environ["SQUORD_GUILD_ID"]

    # Envia um relatório com embed e anexo (upload de 3 passos):
    report_path = "relatorio.txt"
    with open(report_path, "w") as fh:
        fh.write("todos os serviços operacionais\n")

    upload = await client.uploads.upload(
        guild_id=guild_id,
        path=report_path,
        filename="relatorio.txt",
        content_type="text/plain",
    )

    embed = (
        squord.EmbedBuilder()
        .set_title("Relatório diário")
        .set_description("Todos os serviços operacionais.")
        .set_color(0x2ECC71)
        .add_field("API", "Online", inline=True)
        .add_field("Gateway", "Online", inline=True)
        .set_timestamp()
    )

    await client.messages.send(
        channel_id,
        {
            "content": "Atualização de infraestrutura",
            "embeds": [embed],
            "attachmentIds": [upload["id"]],
        },
    )

    print("Relatório publicado.")
    await client.destroy()


if __name__ == "__main__":
    asyncio.run(main())
