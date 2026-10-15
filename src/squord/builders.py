"""Builders tipados: embeds, componentes e payload de mensagens.

Os builders validam localmente os limites reais da plataforma (antes de
gastar uma chamada com um ``422 VALIDATION_FAILED``): 10 embeds por
mensagem, 25 campos por embed, título 256, descrição 4096, nome de campo
256, valor de campo 1024, rodapé 2048, autor 256, 6000 caracteres somados,
5 linhas de componentes, 5 botões por linha ou 1 menu, ``customId`` 100.
"""

from __future__ import annotations

import re
from typing import Any

from .enums import ButtonStyle
from .errors import SquordTypeError
from .types import AllowedMentions, APIEmbedInput

EMBED_LIMITS = {
    "embeds_per_message": 10,
    "fields_per_embed": 25,
    "title": 256,
    "description": 4096,
    "field_name": 256,
    "field_value": 1024,
    "footer_text": 2048,
    "author_name": 256,
    "total_text_per_message": 6000,
}

COMPONENT_LIMITS = {
    "rows_per_message": 5,
    "buttons_per_row": 5,
    "custom_id": 100,
    "label": 80,
    "options_per_menu": 25,
}

_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")
_HTTP_URL_RE = re.compile(r"^https?://")


def normalize_embed_color(color: int | str) -> int:
    """Converte cores: ``#rrggbb`` → inteiro; valida o intervalo."""
    if isinstance(color, bool):
        msg = "Cor de embed precisa ser int ou '#rrggbb'"
        raise SquordTypeError(msg)
    if isinstance(color, int):
        if not 0 <= color <= 0xFF_FF_FF:
            msg = f'Cor de embed inválida: {color} — use um inteiro de 0 a 16777215 ou "#rrggbb"'
            raise SquordTypeError(msg)
        return color
    trimmed = color[1:] if color.startswith("#") else color
    if not _COLOR_RE.match(trimmed):
        msg = f'Cor de embed inválida: {color!r} — use "#rrggbb"'
        raise SquordTypeError(msg)
    return int(trimmed, 16)


def _assert_length(field: str, value: str, limit: int) -> None:
    if len(value) > limit:
        msg = f"Embed.{field} excede {limit} caracteres ({len(value)})"
        raise SquordTypeError(msg)


def _assert_http_url(field: str, url: str) -> None:
    if not _HTTP_URL_RE.match(url):
        msg = f"Embed.{field} precisa ser http:// ou https:// (recebido: {url})"
        raise SquordTypeError(msg)


class EmbedBuilder:
    """Monta embeds com validação dos limites reais do Squord."""

    def __init__(self) -> None:
        self._title: str | None = None
        self._description: str | None = None
        self._url: str | None = None
        self._color: int | None = None
        self._timestamp: str | None = None
        self._author: dict[str, Any] | None = None
        self._footer: dict[str, Any] | None = None
        self._image: str | None = None
        self._thumbnail: str | None = None
        self._fields: list[dict[str, Any]] = []

    def set_title(self, title: str) -> EmbedBuilder:
        _assert_length("title", title, EMBED_LIMITS["title"])
        self._title = title
        return self

    def set_description(self, description: str) -> EmbedBuilder:
        _assert_length("description", description, EMBED_LIMITS["description"])
        self._description = description
        return self

    def set_url(self, url: str) -> EmbedBuilder:
        _assert_http_url("url", url)
        self._url = url
        return self

    def set_color(self, color: int | str) -> EmbedBuilder:
        self._color = normalize_embed_color(color)
        return self

    def set_timestamp(self, timestamp: str | None = None, *, now: bool = True) -> EmbedBuilder:
        """Momento exibido no rodapé: string ISO ou a data atual."""
        if timestamp is None and not now:  # pragma: no cover — guard
            return self
        from datetime import datetime, timezone

        self._timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        return self

    def set_author(
        self,
        name: str,
        *,
        url: str | None = None,
        icon_url: str | None = None,
    ) -> EmbedBuilder:
        _assert_length("author.name", name, EMBED_LIMITS["author_name"])
        if url:
            _assert_http_url("author.url", url)
        self._author = {"name": name}
        if url:
            self._author["url"] = url
        if icon_url:
            self._author["icon_url"] = icon_url
        return self

    def set_footer(self, text: str, *, icon_url: str | None = None) -> EmbedBuilder:
        _assert_length("footer.text", text, EMBED_LIMITS["footer_text"])
        self._footer = {"text": text}
        if icon_url:
            self._footer["icon_url"] = icon_url
        return self

    def set_image(self, url: str) -> EmbedBuilder:
        self._image = url
        return self

    def set_thumbnail(self, url: str) -> EmbedBuilder:
        self._thumbnail = url
        return self

    def add_field(self, name: str, value: str, *, inline: bool = False) -> EmbedBuilder:
        return self.add_fields({"name": name, "value": value, "inline": inline})

    def add_fields(self, *fields: dict[str, Any]) -> EmbedBuilder:
        if len(self._fields) + len(fields) > EMBED_LIMITS["fields_per_embed"]:
            msg = f"Um embed aceita no máximo {EMBED_LIMITS['fields_per_embed']} campos"
            raise SquordTypeError(msg)
        for field in fields:
            _assert_length("field.name", str(field.get("name", "")), EMBED_LIMITS["field_name"])
            _assert_length("field.value", str(field.get("value", "")), EMBED_LIMITS["field_value"])
            self._fields.append(
                {
                    "name": field["name"],
                    "value": field["value"],
                    "inline": bool(field.get("inline", False)),
                }
            )
        return self

    def clear_fields(self) -> EmbedBuilder:
        self._fields = []
        return self

    @property
    def text_length(self) -> int:
        """Soma dos textos do embed (para conferir o limite de 6000)."""
        total = 0
        if self._title:
            total += len(self._title)
        if self._description:
            total += len(self._description)
        if self._footer:
            total += len(self._footer["text"])
        if self._author:
            total += len(str(self._author["name"]))
        for field in self._fields:
            total += len(str(field["name"])) + len(str(field["value"]))
        return total

    def build(self) -> APIEmbedInput:
        """Payload pronto para o campo ``embeds`` (só campos preenchidos)."""
        if not (
            self._title
            or self._description
            or self._image
            or self._thumbnail
            or self._fields
            or self._footer
            or self._author
        ):
            msg = (
                "O embed não tem nada visível: defina título, descrição, campos, "
                "imagem ou rodapé (o Squord recusa embeds vazios com BLANK)"
            )
            raise SquordTypeError(msg)
        embed: dict[str, Any] = {}
        if self._title:
            embed["title"] = self._title
        if self._description:
            embed["description"] = self._description
        if self._url:
            embed["url"] = self._url
        if self._color is not None:
            embed["color"] = self._color
        if self._timestamp:
            embed["timestamp"] = self._timestamp
        if self._author:
            embed["author"] = dict(self._author)
        if self._footer:
            embed["footer"] = dict(self._footer)
        if self._image:
            embed["image"] = {"url": self._image}
        if self._thumbnail:
            embed["thumbnail"] = {"url": self._thumbnail}
        if self._fields:
            embed["fields"] = [dict(f) for f in self._fields]
        return embed  # type: ignore[return-value]

    @classmethod
    def from_embed(cls, embed: dict[str, Any]) -> EmbedBuilder:
        """Cria um builder a partir de um payload existente."""
        builder = cls()
        if embed.get("title"):
            builder.set_title(str(embed["title"]))
        if embed.get("description"):
            builder.set_description(str(embed["description"]))
        if embed.get("url"):
            builder.set_url(str(embed["url"]))
        if embed.get("color") is not None:
            builder.set_color(embed["color"])
        if embed.get("timestamp"):
            builder.set_timestamp(str(embed["timestamp"]))
        author: dict[str, Any] = dict(embed.get("author") or {})
        if author.get("name"):
            builder.set_author(
                str(author["name"]),
                url=author.get("url"),
                icon_url=author.get("iconUrl") or author.get("icon_url"),
            )
        footer: dict[str, Any] = dict(embed.get("footer") or {})
        if footer.get("text"):
            builder.set_footer(
                str(footer["text"]),
                icon_url=footer.get("iconUrl") or footer.get("icon_url"),
            )
        for field in embed.get("fields") or []:
            builder.add_fields(dict(field))
        image = embed.get("image") or {}
        if image.get("url"):
            builder.set_image(str(image["url"]))
        thumbnail: dict[str, Any] = dict(embed.get("thumbnail") or {})
        if thumbnail.get("url"):
            builder.set_thumbnail(str(thumbnail["url"]))
        return builder


def _assert_custom_id(custom_id: str) -> None:
    if not isinstance(custom_id, str) or not 1 <= len(custom_id) <= COMPONENT_LIMITS["custom_id"]:
        msg = f"customId precisa ter de 1 a {COMPONENT_LIMITS['custom_id']} caracteres"
        raise SquordTypeError(msg)


class ButtonBuilder:
    """Botão de ação (``primary``, ``secondary``, ``danger``) ou de link."""

    def __init__(self, style: ButtonStyle | str, label: str) -> None:
        self._style = str(style)
        self._label = label
        self._custom_id: str | None = None
        self._url: str | None = None
        self._disabled = False

    def set_custom_id(self, custom_id: str) -> ButtonBuilder:
        _assert_custom_id(custom_id)
        self._custom_id = custom_id
        return self

    def set_url(self, url: str) -> ButtonBuilder:
        if not url.startswith("https://"):
            msg = f"Botão de link exige URL https:// (recebido: {url})"
            raise SquordTypeError(msg)
        self._url = url
        return self

    def set_disabled(self, disabled: bool = True) -> ButtonBuilder:
        self._disabled = disabled
        return self

    def set_label(self, label: str) -> ButtonBuilder:
        self._label = label
        return self

    def build(self) -> dict[str, Any]:
        if len(self._label) > COMPONENT_LIMITS["label"]:
            msg = f"Label de botão excede {COMPONENT_LIMITS['label']} caracteres"
            raise SquordTypeError(msg)
        if self._style == "link":
            if not self._url:
                msg = "Botão de link exige set_url(...)"
                raise SquordTypeError(msg)
            return {
                "type": "button",
                "style": "link",
                "label": self._label,
                "url": self._url,
                **({"disabled": True} if self._disabled else {}),
            }
        if not self._custom_id:
            msg = f"Botão de estilo {self._style} exige set_custom_id(...)"
            raise SquordTypeError(msg)
        button: dict[str, Any] = {
            "type": "button",
            "style": self._style,
            "label": self._label,
            "customId": self._custom_id,
        }
        if self._disabled:
            button["disabled"] = True
        return button


class Buttons:
    """Atalhos para botões dos quatro estilos."""

    @staticmethod
    def primary(label: str) -> ButtonBuilder:
        return ButtonBuilder("primary", label)

    @staticmethod
    def secondary(label: str) -> ButtonBuilder:
        return ButtonBuilder("secondary", label)

    @staticmethod
    def danger(label: str) -> ButtonBuilder:
        return ButtonBuilder("danger", label)

    @staticmethod
    def link(label: str) -> ButtonBuilder:
        return ButtonBuilder("link", label)


class SelectMenuBuilder:
    """Menu de seleção (ocupa a linha sozinho)."""

    def __init__(self, custom_id: str) -> None:
        _assert_custom_id(custom_id)
        self._custom_id = custom_id
        self._placeholder: str | None = None
        self._min_values: int | None = None
        self._max_values: int | None = None
        self._disabled = False
        self._options: list[dict[str, Any]] = []

    def set_placeholder(self, placeholder: str) -> SelectMenuBuilder:
        if len(placeholder) > 150:
            msg = "Placeholder de menu excede 150 caracteres"
            raise SquordTypeError(msg)
        self._placeholder = placeholder
        return self

    def set_min_values(self, min_values: int) -> SelectMenuBuilder:
        self._min_values = min_values
        return self

    def set_max_values(self, max_values: int) -> SelectMenuBuilder:
        self._max_values = max_values
        return self

    def set_disabled(self, disabled: bool = True) -> SelectMenuBuilder:
        self._disabled = disabled
        return self

    def add_option(
        self, label: str, value: str, *, description: str | None = None
    ) -> SelectMenuBuilder:
        if len(self._options) >= COMPONENT_LIMITS["options_per_menu"]:
            msg = f"Menu aceita no máximo {COMPONENT_LIMITS['options_per_menu']} opções"
            raise SquordTypeError(msg)
        if not label or not value:
            msg = "Opção de menu exige label e value"
            raise SquordTypeError(msg)
        if len(label) > COMPONENT_LIMITS["label"] or len(value) > 100:
            msg = "Label de opção: até 80 caracteres; value: até 100"
            raise SquordTypeError(msg)
        option: dict[str, Any] = {"label": label, "value": value}
        if description:
            option["description"] = description
        self._options.append(option)
        return self

    def build(self) -> dict[str, Any]:
        if not self._options:
            msg = "Menu de seleção precisa de ao menos uma opção"
            raise SquordTypeError(msg)
        min_values = self._min_values if self._min_values is not None else 1
        max_values = (
            self._max_values if self._max_values is not None else max(1, len(self._options))
        )
        if min_values > max_values:
            msg = f"minValues ({min_values}) não pode passar de maxValues ({max_values})"
            raise SquordTypeError(msg)
        menu: dict[str, Any] = {
            "type": "select",
            "customId": self._custom_id,
            "options": [dict(option) for option in self._options],
        }
        if self._placeholder:
            menu["placeholder"] = self._placeholder
        if self._min_values is not None:
            menu["minValues"] = self._min_values
        if self._max_values is not None:
            menu["maxValues"] = self._max_values
        if self._disabled:
            menu["disabled"] = True
        return menu


class ActionRowBuilder:
    """Linha de componentes: 1 a 5 botões **ou** exatamente 1 menu."""

    def __init__(self) -> None:
        self._components: list[dict[str, Any]] = []

    def add_button(self, button: ButtonBuilder | dict[str, Any]) -> ActionRowBuilder:
        if len(self._components) >= COMPONENT_LIMITS["buttons_per_row"] or any(
            c.get("type") == "select" for c in self._components
        ):
            msg = "Uma linha aceita até 5 botões e não mistura botões com menus"
            raise SquordTypeError(msg)
        self._components.append(
            button.build() if isinstance(button, ButtonBuilder) else dict(button)
        )
        return self

    def set_select_menu(self, menu: SelectMenuBuilder | dict[str, Any]) -> ActionRowBuilder:
        if self._components:
            msg = "Um menu ocupa a linha sozinho; não misture com botões"
            raise SquordTypeError(msg)
        self._components.append(menu.build() if isinstance(menu, SelectMenuBuilder) else dict(menu))
        return self

    def build(self) -> dict[str, Any]:
        if not self._components:
            msg = "Linha de componentes vazia"
            raise SquordTypeError(msg)
        return {"type": "row", "components": [dict(c) for c in self._components]}


# --------------------------------------------------------------------- --
# Payload de mensagens
# --------------------------------------------------------------------- --

SAFE_ALLOWED_MENTIONS: AllowedMentions = {"users": True, "roles": False, "everyone": False}

MessagePayload = dict[str, Any]


def resolve_message_payload(
    payload: str | MessagePayload | EmbedBuilder | None,
) -> dict[str, Any]:
    """Normaliza string, builder ou dicionário no corpo aceito pela API.

    Menções seguras por padrão: sem ``allowedMentions`` explícito, o SDK
    envia ``{users: true, roles: false, everyone: false}``.
    """
    source: dict[str, Any]
    if payload is None:
        source = {}
    elif isinstance(payload, str):
        source = {"content": payload}
    elif isinstance(payload, EmbedBuilder):
        source = {"embeds": [payload]}
    else:
        source = dict(payload)

    body: dict[str, Any] = {}
    has_visible = False

    content = source.get("content")
    if content is not None:
        if not isinstance(content, str):
            msg = "content precisa ser string"
            raise SquordTypeError(msg)
        if len(content) > 4_000:
            msg = f"content excede 4000 caracteres ({len(content)})"
            raise SquordTypeError(msg)
        body["content"] = content
        if content:
            has_visible = True

    embeds = source.get("embeds")
    if embeds is not None:
        embeds_list = list(embeds)
        if len(embeds_list) > EMBED_LIMITS["embeds_per_message"]:
            msg = f"embeds aceita até {EMBED_LIMITS['embeds_per_message']} itens"
            raise SquordTypeError(msg)
        body["embeds"] = [
            e.build() if isinstance(e, EmbedBuilder) else dict(e) for e in embeds_list
        ]
        if body["embeds"]:
            has_visible = True

    components = source.get("components")
    if components is not None:
        components_list = list(components)
        if len(components_list) > COMPONENT_LIMITS["rows_per_message"]:
            msg = f"components aceita até {COMPONENT_LIMITS['rows_per_message']} linhas"
            raise SquordTypeError(msg)
        body["components"] = [
            c.build() if isinstance(c, ActionRowBuilder) else dict(c) for c in components_list
        ]
        if body["components"]:
            has_visible = True

    body["allowedMentions"] = dict(source.get("allowedMentions") or SAFE_ALLOWED_MENTIONS)

    if "replyToId" in source and source["replyToId"] is not None:
        body["replyToId"] = source["replyToId"]

    attachment_ids = source.get("attachmentIds")
    if attachment_ids is not None:
        attachment_list = list(attachment_ids)
        if len(attachment_list) > 10:
            msg = "attachmentIds aceita até 10 itens"
            raise SquordTypeError(msg)
        body["attachmentIds"] = attachment_list
        if attachment_list:
            has_visible = True

    if source.get("nonce") is not None:
        nonce = source["nonce"]
        if not isinstance(nonce, str) or len(nonce) > 64:
            msg = "nonce precisa ser string de até 64 caracteres"
            raise SquordTypeError(msg)
        body["nonce"] = nonce

    if source.get("ephemeral") is not None:
        body["ephemeral"] = bool(source["ephemeral"])

    if not has_visible:
        msg = (
            "A mensagem precisa de ao menos um entre content (não vazio), "
            "embeds, components e attachmentIds"
        )
        raise SquordTypeError(msg)

    return body


def resolve_message_edit_payload(payload: str | dict[str, Any] | EmbedBuilder) -> dict[str, Any]:
    """Corpo de edição: o que não for informado continua como estava."""
    source: dict[str, Any]
    if isinstance(payload, str):
        source = {"content": payload}
    elif isinstance(payload, EmbedBuilder):
        source = {"embeds": [payload]}
    else:
        source = dict(payload)

    body: dict[str, Any] = {}
    has_field = False
    if source.get("content") is not None:
        content = source["content"]
        if len(content) > 4_000:
            msg = f"content excede 4000 caracteres ({len(content)})"
            raise SquordTypeError(msg)
        body["content"] = content
        has_field = True
    if source.get("embeds") is not None:
        body["embeds"] = [
            e.build() if isinstance(e, EmbedBuilder) else dict(e) for e in list(source["embeds"])
        ]
        has_field = True
    if source.get("components") is not None:
        body["components"] = [
            c.build() if isinstance(c, ActionRowBuilder) else dict(c)
            for c in list(source["components"])
        ]
        has_field = True
    if source.get("allowedMentions") is not None:
        body["allowedMentions"] = dict(source["allowedMentions"])
    if not has_field:
        msg = "Edição precisa de ao menos um entre content, embeds e components (EMPTY_UPDATE)"
        raise SquordTypeError(msg)
    return body


def safe_allowed_mentions(allowed: AllowedMentions | None = None) -> AllowedMentions:
    """Menções seguras quando o payload não especifica."""
    source = allowed if allowed is not None else SAFE_ALLOWED_MENTIONS
    return {
        "users": bool(source.get("users", True)),
        "roles": bool(source.get("roles", False)),
        "everyone": bool(source.get("everyone", False)),
    }


__all__ = [
    "COMPONENT_LIMITS",
    "EMBED_LIMITS",
    "ActionRowBuilder",
    "ButtonBuilder",
    "Buttons",
    "EmbedBuilder",
    "SelectMenuBuilder",
    "normalize_embed_color",
    "resolve_message_edit_payload",
    "resolve_message_payload",
    "safe_allowed_mentions",
]
