"""Integração: fluxo completo de uploads (reserva → bytes → confirmação → anexo)."""

import pytest

from squord import SquordClient
from squord.testing import create_mock_environment, fixtures

TOKEN = "sqb_1300000000000000010.demo"
CONTENT = b"conteudo do relatorio"


def upload_routes(rest) -> dict:
    state = {"confirmed": 0, "put": None}

    def reserve(match):
        body = match.body
        assert body["scope"] == "attachments"
        assert body["guildId"] == "1300000000000000001"
        assert body["size"] == len(CONTENT)
        state["filename"] = body["filename"]
        return {"status": 201, "body": fixtures.upload_reservation({"filename": body["filename"], "size": len(CONTENT)})}

    def put_bytes(match):
        state["put"] = {
            "path": match.call.path,
            "headers": dict(match.call.headers),
            "size": len(match.body) if isinstance(match.body, bytes) else 0,
        }
        return {"status": 200, "body": {}}

    def confirm(match):
        state["confirmed"] += 1
        return {
            "status": 200,
            "body": fixtures.upload_ready({"filename": state["filename"], "size": len(CONTENT)}),
        }

    rest.on("POST", "/uploads", reserve)
    rest.on("PUT", "/attachments/:key", put_bytes)
    rest.on("POST", "/uploads/:upload_id/confirm", confirm)
    return state


class TestUploadCompleto:
    async def test_fluxo_de_tres_passos(self, tmp_path):
        env = create_mock_environment()
        state = upload_routes(env.rest)
        sent = {}

        def send(match):
            sent.update(match.body)
            return {"status": 201, "body": fixtures.message({"content": match.body.get("content")})}

        env.rest.on("POST", "/channels/:channel_id/messages", send)
        client = SquordClient(token=TOKEN, **env.client_kwargs())
        await client.login()

        upload = await client.uploads.upload(
            guild_id="1300000000000000001",
            data=CONTENT,
            filename="relatorio.pdf",
            content_type="application/pdf",
        )
        assert upload["status"] == "READY"
        assert state["confirmed"] == 1
        assert state["put"]["headers"]["Content-Type"] == "application/pdf"
        assert "Authorization" not in state["put"]["headers"]  # PUT externo sem o token do bot
        assert state["put"]["size"] == len(CONTENT)

        # Confirmação idempotente: repetir devolve o mesmo resultado.
        await client.uploads.confirm(upload["id"])
        assert state["confirmed"] == 2

        await client.messages.send(
            "1300000000000000040", {"content": "Segue o relatório.", "attachmentIds": [upload["id"]]}
        )
        assert sent["attachmentIds"] == [upload["id"]]
        await client.destroy()

    async def test_upload_por_caminho_de_arquivo(self, tmp_path):
        path = tmp_path / "relat.txt"
        path.write_bytes(CONTENT)
        env = create_mock_environment()
        upload_routes(env.rest)
        client = SquordClient(token=TOKEN, **env.client_kwargs())
        await client.login()

        upload = await client.uploads.upload(guild_id="1300000000000000001", path=str(path))
        assert upload["filename"] == "relat.txt"
        await client.destroy()

    async def test_falha_no_put_dos_bytes_nao_confirma(self):
        env = create_mock_environment()
        rest = env.rest

        def reserve(match):
            return {"status": 201, "body": fixtures.upload_reservation()}

        rest.on("POST", "/uploads", reserve)
        rest.on("PUT", "/attachments/:key", lambda m: {"status": 500, "body": "boom"})
        confirmed = []
        rest.on("POST", "/uploads/:id/confirm", lambda m: confirmed.append(1) or {"status": 200, "body": {}})

        client = SquordClient(token=TOKEN, **env.client_kwargs())
        await client.login()
        with pytest.raises(RuntimeError, match="500"):
            await client.uploads.upload(guild_id="g", data=CONTENT)
        assert confirmed == []  # nunca chegou a confirmar
        await client.destroy()

    async def test_validacoes_locais(self):
        env = create_mock_environment()
        client = SquordClient(token=TOKEN, **env.client_kwargs())
        await client.login()

        with pytest.raises(ValueError, match="path ou data"):
            await client.uploads.upload(guild_id="g")
        with pytest.raises(ValueError, match="vazio"):
            await client.uploads.upload(guild_id="g", data=b"")
        with pytest.raises(ValueError, match="500 MB"):
            await client.uploads.upload(guild_id="g", data=b"x" * 524_288_001)
        await client.destroy()


class TestChannelSendFile:
    async def test_atalho_do_canal_envia_anexo_com_conteudo(self):
        env = create_mock_environment()
        state = upload_routes(env.rest)
        sent = {}

        def send(match):
            sent.update(match.body)
            return {"status": 201, "body": fixtures.message({"content": (match.body or {}).get("content", "")})}

        env.rest.on("POST", "/channels/:channel_id/messages", send)
        client = SquordClient(token=TOKEN, **env.client_kwargs())
        await client.login()

        channel = await client.channels.fetch("1300000000000000040")
        from squord.models import Channel

        message = await Channel(client, channel).send_file(data=CONTENT, filename="a.txt", content="olá")
        assert message.content == "olá"
        assert sent["attachmentIds"] == ["1300000000000000300"]
        assert state["confirmed"] == 1
        await client.destroy()
