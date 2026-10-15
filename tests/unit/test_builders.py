"""Testes unitários dos builders: embeds, componentes e payload de mensagens."""

import pytest

from squord.builders import (
    EMBED_LIMITS,
    ActionRowBuilder,
    ButtonBuilder,
    Buttons,
    EmbedBuilder,
    SelectMenuBuilder,
    normalize_embed_color,
    resolve_message_edit_payload,
    resolve_message_payload,
)
from squord.errors import SquordTypeError


class TestEmbedBuilder:
    def test_monta_embed_valido(self):
        embed = (
            EmbedBuilder()
            .set_title("Status do servidor")
            .set_description("Todos os serviços estão operacionais.")
            .set_color(0xF5A623)
            .add_field("API", "Online", inline=True)
            .add_field("Gateway", "Online", inline=True)
            .set_timestamp("2026-10-05T14:30:00.000Z")
        )
        built = embed.build()
        assert built["title"] == "Status do servidor"
        assert built["color"] == 0xF5A623
        assert len(built["fields"]) == 2
        assert built["fields"][0]["inline"] is True
        assert built["timestamp"] == "2026-10-05T14:30:00.000Z"

    def test_cor_em_hex(self):
        assert EmbedBuilder().set_title("x").set_color("#ff579a").build()["color"] == 0xFF579A

    def test_recusa_cor_invalida(self):
        with pytest.raises(SquordTypeError):
            normalize_embed_color("#ff579")
        with pytest.raises(SquordTypeError):
            normalize_embed_color(16_777_216)

    def test_valida_limites_reais(self):
        with pytest.raises(SquordTypeError, match="256"):
            EmbedBuilder().set_title("a" * 257)
        with pytest.raises(SquordTypeError, match="4096"):
            EmbedBuilder().set_description("a" * 4097)
        builder = EmbedBuilder().set_title("x")
        with pytest.raises(SquordTypeError, match="25"):
            builder.add_fields(*[{"name": f"f{i}", "value": "v"} for i in range(26)])

    def test_recusa_embed_vazio_blank(self):
        with pytest.raises(SquordTypeError, match="nada visível"):
            EmbedBuilder().build()

    def test_exige_http_em_url(self):
        with pytest.raises(SquordTypeError, match="http"):
            EmbedBuilder().set_url("ftp://example.com")

    def test_text_length(self):
        embed = EmbedBuilder().set_title("t" * 256).set_description("d" * 4096)
        assert embed.text_length == 256 + 4096

    def test_somente_campos_preenchidos(self):
        built = EmbedBuilder().set_title("t").build()
        assert "description" not in built
        assert "fields" not in built

    def test_from_embed_roundtrip(self):
        original = (
            EmbedBuilder()
            .set_title("Título")
            .set_author("Ana", url="https://a.test", icon_url="https://i.test/png")
            .set_footer("Rodapé")
            .add_field("a", "b")
            .set_image("https://img.test/x.png")
            .build()
        )
        rebuilt = EmbedBuilder.from_embed(dict(original)).build()
        assert rebuilt["title"] == "Título"
        assert rebuilt["author"] == original["author"]
        assert rebuilt["footer"] == {"text": "Rodapé"}
        assert rebuilt["image"] == {"url": "https://img.test/x.png"}

    def test_limites_exportados(self):
        assert EMBED_LIMITS["fields_per_embed"] == 25
        assert EMBED_LIMITS["total_text_per_message"] == 6000


class TestComponentes:
    def test_botao_de_acao_exige_custom_id(self):
        with pytest.raises(SquordTypeError):
            Buttons.primary("Confirmar").build()
        assert Buttons.primary("Confirmar").set_custom_id("ok").build()["customId"] == "ok"

    def test_botao_link_exige_https_e_sem_custom_id(self):
        with pytest.raises(SquordTypeError):
            Buttons.link("Site").build()
        with pytest.raises(SquordTypeError, match="https"):
            Buttons.link("Site").set_url("http://x.test")
        button = Buttons.link("Site").set_url("https://x.test").build()
        assert button["url"] == "https://x.test"
        assert "customId" not in button

    def test_linha_aceita_ate_5_botoes(self):
        row = ActionRowBuilder()
        for i in range(5):
            row.add_button(Buttons.primary(f"b{i}").set_custom_id(f"c{i}"))
        assert len(row.build()["components"]) == 5
        with pytest.raises(SquordTypeError, match="5"):
            row.add_button(Buttons.primary("b6").set_custom_id("c6"))

    def test_menu_ocupa_a_linha_sozinho(self):
        menu = SelectMenuBuilder("tema").add_option("Claro", "claro")
        row = ActionRowBuilder()
        row.add_button(Buttons.primary("x").set_custom_id("x"))
        with pytest.raises(SquordTypeError, match="sozinho"):
            row.set_select_menu(menu)

    def test_menu_valida_min_max_e_opcoes(self):
        menu = SelectMenuBuilder("tema")
        with pytest.raises(SquordTypeError, match="ao menos uma opção"):
            menu.build()
        menu.add_option("A", "a").add_option("B", "b")
        menu.set_min_values(5).set_max_values(1)
        with pytest.raises(SquordTypeError, match="minValues"):
            menu.build()

    def test_custom_id_limites(self):
        with pytest.raises(SquordTypeError, match="customId"):
            ButtonBuilder("primary", "x").set_custom_id("")
        with pytest.raises(SquordTypeError, match="customId"):
            SelectMenuBuilder("c" * 101)


class TestResolveMessagePayload:
    def test_string_vira_content(self):
        assert resolve_message_payload("olá")["content"] == "olá"

    def test_builders_e_mencoes_seguras(self):
        embed = EmbedBuilder().set_title("t")
        row = ActionRowBuilder().add_button(Buttons.primary("ok").set_custom_id("ok"))
        payload = resolve_message_payload(
            {"content": "Atualização", "embeds": [embed], "components": [row]}
        )
        assert payload["embeds"] == [{"title": "t"}]
        assert payload["components"][0]["components"][0]["customId"] == "ok"
        assert payload["allowedMentions"] == {"users": True, "roles": False, "everyone": False}

    def test_mencoes_customizadas_sao_respeitadas(self):
        payload = resolve_message_payload(
            {"content": "x", "allowedMentions": {"users": False, "roles": True, "everyone": True}}
        )
        assert payload["allowedMentions"] == {"users": False, "roles": True, "everyone": True}

    def test_recusa_payload_sem_conteudo_visivel(self):
        with pytest.raises(SquordTypeError):
            resolve_message_payload({"content": ""})
        with pytest.raises(SquordTypeError):
            resolve_message_payload({})

    def test_valida_limites(self):
        with pytest.raises(SquordTypeError, match="4000"):
            resolve_message_payload({"content": "a" * 4001})
        with pytest.raises(SquordTypeError, match="10"):
            resolve_message_payload({"content": "x", "attachmentIds": [str(i) for i in range(11)]})

    def test_nonce_e_reply_preservados(self):
        payload = resolve_message_payload(
            {"content": "r", "replyToId": "1300000000000000100", "nonce": "chave"}
        )
        assert payload["replyToId"] == "1300000000000000100"
        assert payload["nonce"] == "chave"

    def test_nonce_invalido(self):
        with pytest.raises(SquordTypeError, match="nonce"):
            resolve_message_payload({"content": "x", "nonce": "c" * 65})

    def test_edit_payload(self):
        body = resolve_message_edit_payload({"content": "novo", "embeds": []})
        assert body["content"] == "novo"
        assert body["embeds"] == []
        with pytest.raises(SquordTypeError, match="EMPTY_UPDATE"):
            resolve_message_edit_payload({})

    def test_embed_builder_direto_no_payload(self):
        payload = resolve_message_payload({"embeds": [EmbedBuilder().set_title("direto")]})
        assert payload["embeds"] == [{"title": "direto"}]


class TestEventEmitterDecorator:
    """Os dois estilos de registro: direto e decorador (usado nos exemplos)."""

    async def test_on_como_decorador(self):
        from squord.events import EventEmitter

        emitter = EventEmitter()
        received = []

        @emitter.on("ready")
        async def handler(payload):
            received.append(payload)

        await emitter.emit("ready", "ok")
        assert received == ["ok"]
        # O decorador devolve a função original (pode ser reutilizada).
        assert handler.__name__ == "handler"

    async def test_on_direto_devolve_dispose(self):
        from squord.events import EventEmitter

        emitter = EventEmitter()
        received = []

        async def handler(payload):
            received.append(payload)

        dispose = emitter.on("ready", handler)
        await emitter.emit("ready", "um")
        dispose()
        await emitter.emit("ready", "dois")
        assert received == ["um"]
