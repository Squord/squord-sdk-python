"""Integração: gateway com o protocolo real simulado."""

import asyncio

import pytest

from squord.errors import GatewayError
from squord.gateway import Gateway
from squord.testing import create_mock_gateway

TOKEN = "sqb_1300000000000000010.segredo"


def make_gateway(**kwargs) -> tuple[Gateway, object]:
    server = create_mock_gateway(
        heartbeat_interval_ms=kwargs.pop("heartbeat_interval_ms", 200), **kwargs
    )
    gateway = Gateway(
        TOKEN,
        connector=server.ws_connector,
        reconnect_base_ms=kwargs.pop("reconnect_base_ms", 20),
    )
    return gateway, server


class TestCicloDeVida:
    async def test_hello_identify_ready(self):
        gateway, _server = make_gateway()
        readies = []
        gateway.on("ready", lambda ready: readies.append(ready))
        ready = await gateway.connect()

        assert len(readies) == 1
        assert ready["sessionId"]
        assert ready["userId"] == "1300000000000000010"
        assert gateway.is_ready
        await gateway.destroy()

    async def test_token_errado_4004_e_nao_reconecta(self):
        _gateway, _ = make_gateway(token=TOKEN)
        other = Gateway("sqb_errado.outro", connector=make_gateway(token=TOKEN)[0]._connector)
        # Usa conector do servidor com token certo
        server = create_mock_gateway(token=TOKEN)
        other = Gateway("sqb_errado.outro", connector=server.ws_connector, reconnect_base_ms=20)
        with pytest.raises(GatewayError) as info:
            await other.connect()
        assert info.value.close_code == 4004
        await asyncio.sleep(0.2)
        assert not other.is_ready
        await other.destroy()

    async def test_heartbeat_ack_medindo_latencia(self):
        gateway, _ = make_gateway(heartbeat_interval_ms=40)
        await gateway.connect()
        for _ in range(50):
            if gateway.heartbeat_latency_ms is not None:
                break
            await asyncio.sleep(0.05)
        assert gateway.heartbeat_latency_ms is not None
        await gateway.destroy()

    async def test_zumbi_sem_ack_fecha_e_retoma_com_resume(self):
        gateway, _ = make_gateway(heartbeat_interval_ms=40, suppress_heartbeat_ack=True)
        await gateway.connect()
        first_session = gateway.session_id
        resumed = asyncio.Event()
        gateway.on("resumed", lambda data: resumed.set())

        # O watchdog de zumbi fecha e o loop retoma com resume.
        await asyncio.wait_for(resumed.wait(), timeout=5)
        assert gateway.session_id == first_session
        assert gateway.is_ready
        await gateway.destroy()

    async def test_queda_4009_retoma_e_reenvia_eventos_perdidos(self):
        gateway, server = make_gateway(heartbeat_interval_ms=500)
        await gateway.connect()

        received: list[tuple[str, int]] = []
        gateway.on("event", lambda t, d, s, ts: received.append((str(t), int(s or 0))))
        server.emit_event("message.created", {"message": {"id": "1"}})
        server.emit_event("message.updated", {"message": {"id": "1"}})
        while len(received) < 2:
            await asyncio.sleep(0.02)
        last_sequence = gateway.sequence
        assert last_sequence == 2

        server.close_all(4009, "session timeout")
        server.emit_event("message.deleted", {"messageId": "1", "channelId": "c", "guildId": "g"})
        server.emit_event(
            "reaction.added",
            {
                "messageId": "1",
                "channelId": "c",
                "guildId": "g",
                "userId": "u",
                "reaction": {"emoji": "👍", "count": 1, "userIds": ["u"], "me": False},
                "customEmoji": None,
            },
        )

        resumed = asyncio.Event()
        gateway.on("resumed", lambda data: resumed.set())
        replayed: list[str] = []
        gateway.on(
            "event",
            lambda t, d, s, ts: replayed.append(str(t)) if (s or 0) > last_sequence else None,
        )

        await asyncio.wait_for(resumed.wait(), timeout=5)
        assert gateway.session_id is not None
        assert replayed == ["message.deleted", "reaction.added"]
        assert gateway.is_ready
        await gateway.destroy()

    async def test_invalid_session_cai_para_identify_na_mesma_conexao(self):
        gateway, _ = make_gateway(heartbeat_interval_ms=500, refuse_resume_once=True)
        await gateway.connect()
        invalids = []
        readies = []
        gateway.on("invalid_session", lambda payload: invalids.append(payload))
        gateway.on("ready", lambda ready: readies.append(ready))

        gateway.reconnect_now()
        # O resume é recusado uma vez → invalid_session → identify → ready novo.
        for _ in range(100):
            if readies:
                break
            await asyncio.sleep(0.05)
        assert readies, "deveria ter feito identify e recebido ready de novo"
        assert gateway.is_ready
        await gateway.destroy()

    async def test_evento_duplicado_e_descartado(self):
        gateway, server = make_gateway(heartbeat_interval_ms=500)
        await gateway.connect()

        delivered: list[int] = []
        gateway.on("event", lambda t, d, s, ts: delivered.append(int(s or 0)))

        server.emit_event("message.created", {"message": {"id": "1"}})
        while not delivered:
            await asyncio.sleep(0.02)
        sequence = delivered[0]

        # Replay com a mesma sequência (e uma anterior): descartado.
        server.send_event_with_sequence("message.created", {"message": {"id": "1"}}, sequence)
        server.send_event_with_sequence("message.created", {"message": {"id": "1"}}, sequence - 1)
        await asyncio.sleep(0.2)

        assert gateway.events_received == 3  # contagem inclui duplicados
        assert gateway.events_dropped == 2
        assert delivered == [sequence]
        assert gateway.sequence == sequence
        await gateway.destroy()

    async def test_reconnect_pedido_pelo_servidor_4007_retoma(self):
        gateway, server = make_gateway(heartbeat_interval_ms=500)
        await gateway.connect()
        session = gateway.session_id
        resumed = asyncio.Event()
        gateway.on("resumed", lambda data: resumed.set())

        server.request_reconnect("gateway shutting down")
        await asyncio.wait_for(resumed.wait(), timeout=5)
        assert gateway.session_id == session
        assert gateway.is_ready
        await gateway.destroy()

    async def test_contadores_para_diagnostico(self):
        gateway, server = make_gateway(heartbeat_interval_ms=500)
        await gateway.connect()
        server.emit_event("message.created", {"message": {"id": "1"}})
        while gateway.events_received < 1:
            await asyncio.sleep(0.02)
        assert gateway.reconnect_count == 0

        server.close_all(4009, "session timeout")
        for _ in range(100):
            if gateway.reconnect_count >= 1:
                break
            await asyncio.sleep(0.05)
        assert gateway.reconnect_count >= 1
        await gateway.destroy()

    async def test_caminho_invalido_levanta_no_conector(self):
        async def bad_connector(url: str):
            raise ValueError("caminho inválido")

        gateway = Gateway(TOKEN, connector=bad_connector, auto_reconnect=False)
        with pytest.raises(GatewayError):
            await gateway.connect()
        await gateway.destroy()
