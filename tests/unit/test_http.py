"""Testes do RestClient contra o MockRest: erros, retries e rate limits."""

import asyncio
import time

import pytest

from squord.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    RequestTimeoutError,
    SquordAPIError,
    ValidationError,
)
from squord.http import (
    RequestOptions,
    RestClient,
    TransportRequest,
    TransportResponse,
    route_key_of,
)
from squord.testing import create_mock_rest

TOKEN = "sqb_1.segredo"


def make_rest(**kwargs) -> tuple[RestClient, object]:
    mock = create_mock_rest()
    defaults = {"base_url": "https://mock.test", "transport": mock}
    defaults.update(kwargs)
    client = RestClient(TOKEN, **defaults)
    return client, mock


class SlowTransport:
    """Transporte que demora mais que o timeout configurado."""

    def __init__(self, delay: float = 0.2) -> None:
        self.delay = delay

    async def request(self, request: TransportRequest) -> TransportResponse:
        await asyncio.sleep(self.delay)
        return TransportResponse(200, {"Content-Type": "application/json"}, b"{}")

    async def close(self) -> None:
        return None


class TestBasico:
    async def test_envia_authorization_content_type_e_request_id(self):
        client, mock = make_rest()
        mock.on("GET", "/bots/@me", lambda m: {"status": 200, "body": {"id": "1"}})
        await client.get("/bots/@me")
        call = mock.last_call  # type: ignore[attr-defined]
        assert call.headers["Authorization"] == f"Bot {TOKEN}"
        assert call.headers["Content-Type"] == "application/json"
        assert call.request_id

    async def test_query_params_e_omissao_de_vazios(self):
        client, mock = make_rest()
        mock.on("GET", "/channels/:id/messages", lambda m: {"status": 200, "body": {}})
        await client.get(
            "/channels/1300000000000000040/messages",
            RequestOptions(query={"limit": 50, "before": None, "after": None}),
        )
        call = mock.last_call  # type: ignore[attr-defined]
        assert call.query["limit"] == "50"
        assert "before" not in call.query

    async def test_corpo_json_serializado(self):
        client, mock = make_rest()
        mock.on("POST", "/channels/:id/messages", lambda m: {"status": 201, "body": m.body})
        result = await client.post("/channels/c1/messages", {"content": "oi", "nonce": "abc"})
        assert result == {"content": "oi", "nonce": "abc"}

    async def test_delete_204_devolve_none(self):
        client, mock = make_rest()
        mock.on("DELETE", "/channels/:id/messages/:mid", lambda m: {"status": 204})
        assert await client.delete("/channels/1/messages/2") is None

    async def test_rota_publica_sem_authorization(self):
        client, mock = make_rest()
        mock.on("POST", "/interactions/:id/:token/callback", lambda m: {"status": 204})
        await client.post("/interactions/i1/tk/callback", {"type": "MESSAGE"}, RequestOptions(auth=False))
        assert "Authorization" not in mock.last_call.headers  # type: ignore[attr-defined]


class TestMapeamentoDeErros:
    async def test_401_vira_authentication_error(self):
        client, mock = make_rest()
        mock.on("GET", "/x", lambda m: {"status": 401, "body": {"code": "INVALID_TOKEN", "message": "no"}})
        with pytest.raises(AuthenticationError) as info:
            await client.get("/x")
        assert info.value.code == "INVALID_TOKEN"
        assert info.value.request_id

    async def test_403_com_detalhe_da_permissao(self):
        client, mock = make_rest()
        mock.on("GET", "/x", lambda m: {
            "status": 403,
            "body": {
                "code": "MISSING_PERMISSION",
                "message": "Missing permission: SEND_MESSAGES",
                "details": {"permission": "SEND_MESSAGES"},
            },
        })
        with pytest.raises(PermissionError) as info:
            await client.get("/x")
        assert info.value.missing_permission == "SEND_MESSAGES"

    async def test_404_vira_not_found(self):
        client, mock = make_rest()
        mock.on("GET", "/x", lambda m: {"status": 404, "body": {"code": "NOT_FOUND", "message": "não"}})
        with pytest.raises(NotFoundError):
            await client.get("/x")

    async def test_422_validacao_com_issues(self):
        client, mock = make_rest()
        mock.on("POST", "/x", lambda m: {
            "status": 422,
            "body": {
                "code": "VALIDATION_FAILED",
                "message": "Request payload failed validation",
                "details": [{"path": "embeds.0.title", "code": "TOO_LONG", "message": "Too long"}],
            },
        })
        with pytest.raises(ValidationError) as info:
            await client.post("/x", {})
        assert info.value.issues[0]["path"] == "embeds.0.title"

    async def test_rota_nao_mockada_devolve_404_do_envelope(self):
        client, _ = make_rest()
        with pytest.raises(SquordAPIError) as info:
            await client.get("/rota-inexistente")
        assert info.value.code == "NOT_FOUND"


class TestPoliticaDeRetentativas:
    async def test_429_espera_retry_after_e_repete(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            if len(calls) == 1:
                return {
                    "status": 429,
                    "body": {"code": "RATE_LIMITED", "message": "slow down",
                             "details": {"bucket": "DEFAULT", "retryAfter": 1}},
                }
            return {"status": 200, "body": {"ok": True}}

        mock.on("GET", "/bots/@me", handler)
        result = await client.get("/bots/@me")
        assert result == {"ok": True}
        assert len(calls) == 2

    async def test_429_esgotado_vira_rate_limit_error(self):
        client, mock = make_rest()
        mock.on("GET", "/x", lambda m: {
            "status": 429,
            "body": {"code": "RATE_LIMITED", "message": "slow",
                     "details": {"bucket": "DEFAULT", "retryAfter": 1}},
        })
        client.max_retries = 1
        with pytest.raises(RateLimitError) as info:
            await client.get("/x")
        assert info.value.retry_after == 1
        assert info.value.bucket == "DEFAULT"
        assert info.value.exhausted_retries is True

    async def test_5xx_repete_em_get(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            if len(calls) <= 2:
                return {"status": 503, "body": {"code": "SERVICE_UNAVAILABLE", "message": "x"}}
            return {"status": 200, "body": {"ok": True}}

        mock.on("GET", "/bots/@me", handler)
        assert await client.get("/bots/@me") == {"ok": True}
        assert len(calls) == 3

    async def test_5xx_nao_repete_post_sem_nonce(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            return {"status": 503, "body": {"code": "SERVICE_UNAVAILABLE", "message": "x"}}

        mock.on("POST", "/uploads", handler)
        with pytest.raises(SquordAPIError):
            await client.post("/uploads", {})
        assert len(calls) == 1

    async def test_5xx_repete_post_protegido_por_nonce(self):
        client, mock = make_rest()
        bodies = []

        def handler(match):
            bodies.append(match.body)
            if len(bodies) == 1:
                return {"status": 503, "body": {"code": "SERVICE_UNAVAILABLE", "message": "x"}}
            return {"status": 201, "body": {"nonce": match.body["nonce"]}}

        mock.on("POST", "/channels/:id/messages", handler)
        result = await client.post(
            "/channels/c1/messages", {"content": "oi", "nonce": "fixo"}, RequestOptions(retryable=True)
        )
        assert result == {"nonce": "fixo"}
        assert [b["nonce"] for b in bodies] == ["fixo", "fixo"]

    async def test_409_commands_conflict_repete(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            if len(calls) == 1:
                return {"status": 409, "body": {"code": "COMMANDS_CONFLICT", "message": "x"}}
            return {"status": 200, "body": []}

        mock.on("PUT", "/bots/@me/commands", handler)
        await client.put("/bots/@me/commands", [])
        assert len(calls) == 2

    async def test_falha_de_rede_repete_idempotente(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("fetch failed")
            return {"status": 200, "body": {"ok": True}}

        mock.on("GET", "/bots/@me", handler)
        assert await client.get("/bots/@me") == {"ok": True}

    async def test_falha_de_rede_em_post_nao_idempotente_falha_direto(self):
        client, mock = make_rest()
        calls = []

        def handler(match):
            calls.append(1)
            raise RuntimeError("fetch failed")

        mock.on("POST", "/uploads", handler)
        with pytest.raises(NetworkError):
            await client.post("/uploads", {})
        assert len(calls) == 1

    async def test_timeout_tipado_nao_repete_post(self):
        client = RestClient(
            TOKEN, base_url="https://mock.test", timeout_ms=50, transport=SlowTransport(delay=0.2)
        )
        with pytest.raises(RequestTimeoutError) as info:
            await client.post("/uploads", {})
        assert info.value.timeout_ms == 50
        await client.close()

    async def test_timeout_repete_get_e_falha_tipado(self):
        client = RestClient(
            TOKEN,
            base_url="https://mock.test",
            timeout_ms=50,
            max_retries=1,
            transport=SlowTransport(delay=0.2),
        )
        with pytest.raises(RequestTimeoutError):
            await client.get("/bots/@me")
        await client.close()


class TestRateLimitsLocais:
    async def test_bloqueia_rota_quando_remaining_zero(self):
        client, mock = make_rest()
        reset_at = int(time.time()) + 1
        calls = []

        def handler(match):
            calls.append(1)
            remaining = "0" if len(calls) == 1 else "1"
            return {
                "status": 200,
                "body": {"seq": len(calls)},
                "headers": {
                    "X-RateLimit-Limit": "2",
                    "X-RateLimit-Remaining": remaining,
                    "X-RateLimit-Reset": str(reset_at),
                },
            }

        mock.on("GET", "/x", handler)
        await client.get("/x")
        # A segunda chamada espera a janela renovar em vez de tomar 429.
        second = asyncio.get_running_loop().create_task(client.get("/x"))
        await asyncio.sleep(1.3)
        await asyncio.wait_for(second, timeout=2)
        assert len(calls) == 2
        assert client.bucket_state("GET", "/x").remaining == 1

    async def test_teto_global_abaixo_de_50_por_segundo(self):
        client, mock = make_rest(global_requests_per_second=5)
        mock.on("GET", "/x", lambda m: {"status": 200, "body": {}})
        start = time.monotonic()
        await asyncio.gather(*[client.get("/x") for _ in range(10)])
        elapsed = time.monotonic() - start
        # 10 requisições com teto de 5/s: precisou esperar ~1 s.
        assert elapsed >= 0.9


class TestRouteKey:
    def test_substitui_ids(self):
        assert route_key_of("POST", "/channels/1300000000000000040/messages") == "POST /channels/{id}/messages"
        assert route_key_of("PUT", "/guilds/12345/bans/67890") == "PUT /guilds/{id}/bans/{id}"

    def test_nao_troca_at_me(self):
        assert route_key_of("GET", "/bots/@me") == "GET /bots/@me"
