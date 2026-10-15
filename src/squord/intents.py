"""Intents do gateway.

As intents são configuradas por bot (Configurações → Desenvolvedor, ou
``PATCH /bots/{bot.id}``) e **não** vão no ``identify``: o gateway lê as
intents do bot no momento do identify. Este módulo serve para calcular,
exibir e comparar valores.

O padrão de um bot novo é ``GUILDS | GUILD_MESSAGES | GUILD_MESSAGE_REACTIONS``
(valor ``13``).

@see https://docs.squord.com.br/gateway/intents
"""

from __future__ import annotations

from enum import IntFlag


class Intents(IntFlag):
    GUILDS = 1 << 0
    GUILD_MEMBERS = 1 << 1
    GUILD_MESSAGES = 1 << 2
    GUILD_MESSAGE_REACTIONS = 1 << 3
    GUILD_VOICE_STATES = 1 << 4
    #: **Privilegiada.** Não liga evento nenhum: devolve o conteúdo das
    #: mensagens. Sem ela, ``content``, ``embeds``, ``attachments``,
    #: ``components`` e ``poll`` chegam esvaziados — exceto mensagens do
    #: próprio bot e as que o mencionam.
    MESSAGE_CONTENT = 1 << 5


#: Intents padrão de um bot novo (valor 13, igual à documentação).
DEFAULT_INTENTS = Intents.GUILDS | Intents.GUILD_MESSAGES | Intents.GUILD_MESSAGE_REACTIONS


def intents_value(*flags: int | Intents) -> int:
    """Soma flags de intent em um número (0 a 65535)."""
    value = 0
    for flag in flags:
        value |= int(flag)
    if not 0 <= value <= 65_535:
        msg = "As intents somam um inteiro de 0 a 65535"
        raise ValueError(msg)
    return value


def list_intents(value: int) -> list[str]:
    """Lista as flags conhecidas presentes em um valor de intents."""
    return [flag.name for flag in Intents if value & int(flag) == int(flag) and flag.name]
