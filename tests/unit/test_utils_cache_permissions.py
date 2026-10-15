"""Testes unitários: utils, cache, permissões, intents e logger."""

import pytest

from squord.cache import Cache
from squord.intents import DEFAULT_INTENTS, Intents, intents_value, list_intents
from squord.logger import redact
from squord.permissions import (
    Permissions,
    has_any_permission,
    has_permissions,
    parse_permissions,
    permissions_to_string,
    resolve_channel_permissions,
)
from squord.utils import (
    backoff_delay,
    compare_snowflakes,
    guess_content_type,
    is_valid_snowflake,
    split_arguments,
    strip_token_prefix,
)


class TestSplitArguments:
    def test_aspas_duplas(self):
        assert split_arguments('ban @ana "motivo longo" 7d') == [
            "ban",
            "@ana",
            "motivo longo",
            "7d",
        ]

    def test_aspas_simples(self):
        assert split_arguments("say 'oi gente' fim") == ["say", "oi gente", "fim"]

    def test_espacos_extras(self):
        assert split_arguments("  a   b  ") == ["a", "b"]

    def test_aspas_nao_fechadas(self):
        assert split_arguments('x "abc') == ["x", "abc"]


class TestSnowflakes:
    def test_valida_formatos(self):
        assert is_valid_snowflake("1300000000000000020")
        assert is_valid_snowflake("6687f7a1c2d3e4f5a6b7c8d9")  # hex 24
        assert not is_valid_snowflake("abc")
        assert not is_valid_snowflake("")

    def test_compara_numericamente_alem_de_2p53(self):
        assert compare_snowflakes("100", "200") < 0
        assert compare_snowflakes("200", "100") > 0
        assert compare_snowflakes("9007199254740993", "9007199254740992") > 0

    def test_strip_token_prefix(self):
        assert strip_token_prefix("Bot sqb_1.x") == "sqb_1.x"
        assert strip_token_prefix("sqb_1.x") == "sqb_1.x"


class TestBackoff:
    def test_cresce_exponencialmente_ate_o_teto(self, monkeypatch):
        monkeypatch.setattr("random.uniform", lambda a, b: 0.5)  # jitter neutro
        assert backoff_delay(0) == 1_000
        assert backoff_delay(1) == 2_000
        assert backoff_delay(2) == 4_000
        assert backoff_delay(6) == 60_000
        assert backoff_delay(20) == 60_000

    def test_jitter_dentro_dos_limites(self):
        for _ in range(30):
            delay = backoff_delay(3, base_ms=1_000, jitter=0.5)
            assert 4_000 <= delay <= 12_000


class TestGuessContentType:
    def test_extensoes_comuns(self):
        assert guess_content_type("a.png") == "image/png"
        assert guess_content_type("relatorio.pdf") == "application/pdf"
        assert guess_content_type("desconhecido.xyz") == "application/octet-stream"


class TestCache:
    def test_guarda_e_recupera(self):
        cache: Cache[str, int] = Cache()
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_expira_pelo_ttl(self):
        now = [1000.0]
        cache: Cache[str, int] = Cache(ttl_ms=500, clock=lambda: now[0])
        cache.set("a", 1)
        now[0] += 400
        assert cache.get("a") == 1
        now[0] += 200
        assert cache.get("a") is None
        assert cache.size == 0

    def test_descarta_os_mais_antigos(self):
        cache: Cache[int, int] = Cache(max_size=3)
        for i in range(1, 5):
            cache.set(i, i)
        assert cache.size == 3
        assert not cache.has(1)
        assert cache.has(4)

    def test_promove_item_acessado(self):
        cache: Cache[str, int] = Cache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        cache.set("c", 3)
        assert cache.has("a")
        assert not cache.has("b")

    def test_delete_clear_items(self):
        cache: Cache[str, int] = Cache()
        cache.set("a", 1)
        assert cache.delete("a") is True
        assert cache.get("a") is None
        cache.set("b", 2)
        cache.clear()
        assert cache.size == 0

    def test_itera_apenas_vivos(self):
        cache: Cache[str, int] = Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert list(cache.items()) == [("a", 1), ("b", 2)]


class TestPermissoes:
    def test_valor_da_documentacao_155649(self):
        bits = (
            Permissions.VIEW_CHANNEL
            | Permissions.SEND_MESSAGES
            | Permissions.READ_MESSAGE_HISTORY
            | Permissions.EMBED_LINKS
        )
        assert permissions_to_string(bits) == "155649"
        assert parse_permissions("155649") == bits

    def test_bit_mais_alto_da_tabela(self):
        assert permissions_to_string(Permissions.MANAGE_EVENTS) == "4398046511104"
        all_bits = int(Permissions.SEND_POLLS) | int(Permissions.MANAGE_EVENTS)
        assert parse_permissions(str(all_bits)) == Permissions(all_bits)

    def test_has_permissions(self):
        bits = Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES
        assert has_permissions(bits, Permissions.VIEW_CHANNEL, Permissions.SEND_MESSAGES)
        assert not has_permissions(bits, Permissions.BAN_MEMBERS)
        assert has_any_permission(bits, Permissions.BAN_MEMBERS, Permissions.SEND_MESSAGES)

    def test_resolve_overwrites_na_ordem_oficial(self):
        result = resolve_channel_permissions(
            everyone_permissions=Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES,
            role_permissions=[],
            overwrites=[
                {"targetId": "role1", "targetType": "ROLE", "allow": "8192", "deny": "0"},
                {"targetId": "user1", "targetType": "MEMBER", "allow": "0", "deny": "8192"},
            ],
            member_id="user1",
            everyone_role_id="g1",
            member_role_ids=["role1"],
        )
        assert has_permissions(result, Permissions.VIEW_CHANNEL)
        assert not has_permissions(result, Permissions.SEND_MESSAGES)

    def test_sem_view_channel_resultado_zero(self):
        result = resolve_channel_permissions(
            everyone_permissions=Permissions.SEND_MESSAGES,
            role_permissions=[],
            overwrites=[{"targetId": "g1", "targetType": "ROLE", "allow": "0", "deny": "1"}],
            member_id="user1",
            everyone_role_id="g1",
            member_role_ids=["g1"],
        )
        assert result == Permissions(0)

    def test_administrator_concede_tudo(self):
        result = resolve_channel_permissions(
            everyone_permissions=Permissions.ADMINISTRATOR,
            role_permissions=[],
            overwrites=[],
            member_id="u",
            everyone_role_id="g",
            member_role_ids=[],
        )
        assert has_permissions(result, Permissions.BAN_MEMBERS, Permissions.MANAGE_GUILD)


class TestIntents:
    def test_padrao_do_bot_novo_e_13(self):
        assert int(DEFAULT_INTENTS) == 13

    def test_soma_bits(self):
        assert intents_value(Intents.GUILDS, Intents.GUILD_MEMBERS, Intents.GUILD_MESSAGES) == 7
        assert intents_value(Intents.GUILDS, Intents.GUILD_MESSAGES, Intents.MESSAGE_CONTENT) == 37

    def test_lista_flags(self):
        assert list_intents(13) == ["GUILDS", "GUILD_MESSAGES", "GUILD_MESSAGE_REACTIONS"]

    def test_recusa_fora_do_intervalo(self):
        with pytest.raises(ValueError, match="65535"):
            intents_value(1 << 20)


class TestLoggerRedaction:
    def test_redige_token_de_bot(self):
        assert redact("Authorization: Bot sqb_1300000000000000010.SEGREDO") == (
            "Authorization: Bot sqb_[REDACTED]"
        )

    def test_redige_token_sozinho(self):
        assert "sqb_1300000000000000010.SEGREDO" not in redact(
            "log com sqb_1300000000000000010.SEGREDO"
        )

    def test_redige_json_token(self):
        assert redact('{"token": "tk_1b3d5f7a9c2e"}') == '{"token":"[REDACTED]"}'

    def test_mensagem_sem_segrredo_permanece(self):
        assert redact("mensagem comum") == "mensagem comum"
