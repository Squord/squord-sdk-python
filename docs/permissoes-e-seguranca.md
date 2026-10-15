# Permissões e segurança

Como o SDK representa o modelo de permissões do Squord — e as proteções que
vêm ligadas por padrão. Referência: <https://docs.squord.com.br/referencia/permissoes>.

## Em Python, permissões são ``IntFlag`` (``int`` já tem precisão arbitrária)

Permissões trafegam como **strings decimais** de 64 bits. Calcule com `BigInt`
(todos os utilitários do SDK fazem isso); nunca com `number`.

```python
import squord
from squord import Permissions

bits = Permissions.VIEW_CHANNEL | Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
str(int(bits))  # "139713" — é isso que vai na API
Permissions(int("155649"))  # string vinda de um cargo
```

As 43 flags documentadas estão em `Permissions`, do `VIEW_CHANNEL` (bit 0) ao
`MANAGE_EVENTS` (bit 42). O bit 32 foi aposentado e nunca é reutilizado.

## Resolução efetiva

Para agir, um bot passa pela mesma cadeia de qualquer membro: conta →
participação no Space → cargos (@everyone + cargos + cargo gerenciado do bot)
→ overwrites de canal → tipo do canal → timeout. Não existe permissão especial
para bots.

```python
# O que o bot tem no nível do Space (bloco self de GET /guilds/{id}):
guild = await client.guilds.fetch(space_id)
if guild.self_permissions & Permissions.BAN_MEMBERS:
    ...

# Resolução local completa, com overwrites (everyone → cargos → membro):
bits = await client.my_permissions_in(channel_id)
can = await client.has_permissions_in(channel_id, Permissions.SEND_MESSAGES, Permissions.EMBED_LINKS)

# O algoritmo oficial também é utilidade pública:
from squord import resolve_channel_permissions
```

A verificação local é conveniência para evitar chamadas fúteis; **o backend é a
autoridade final** — uma recusa chega como `403 MISSING_PERMISSION`
(`PermissionError.missingPermission`) sem gasto de cota à toa.

## Hierarquia

Ter a permissão diz **o quê**; a hierarquia diz **sobre quem**:

- O bot só age sobre membros de posição estritamente menor que a do seu cargo
  gerenciado (`HIERARCHY_BLOCKED`).
- Só atribui cargos abaixo do seu mais alto (`ROLE_ABOVE_ACTOR`).
- O dono do Space é intocável (`OWNER_PROTECTED`).
- Cargos gerenciados (o do bot, o de booster) não são dados nem tirados à mão
  (`ROLE_MANAGED`).

## Menções seguras por padrão

Sem `allowedMentions` explícito, o SDK envia `{ users: true, roles: false,
everyone: false }` — o padrão da plataforma, explícito no payload: conteúdo
arbitrário não dispara notificação de cargos nem `@everyone`. Cargos não
mencionáveis e `@everyone` sem `MENTION_EVERYONE` continuam bloqueados pelo
servidor de qualquer forma.

```python
await channel.send({
    "content": "Sentiram todos? <@&123>",  # cargo removido do texto se roles: false
    "allowedMentions": {"users": True, "roles": False, "everyone": False},  # padrão
})
```

## Segurança embutida no SDK

- **Redação de tokens**: `sqb_...` e headers `Authorization` viram
  `[REDACTED]` em qualquer linha de log. Tokens de interação também.
- **Nunca logar conteúdo de mensagens** por padrão — só metadados operacionais.
- **Validação de ids** (`assertSnowflake`) e de payloads nos limites reais
  (embeds, componentes, `content`, uploads) **antes** de gastar chamadas.
- **Idempotência de envio**: `nonce` automático em cada mensagem — repetir
  após falha de rede não duplica.
- **Nunca repetir o incerto**: POSTs sem garantia (banir, criar thread,
  responder interação) não são reenviados automaticamente.
- **Nada de bypass**: o SDK não tem (e não teria) caminho para contornar
  permissões, hierarquia ou o AutoMod do Space (`AUTOMOD_BLOCKED` chega como
  `ValidationError`).
- **Privilégio mínimo por padrão**: um bot que só atende comandos de barra,
  botões e menções funciona sem a intent `MESSAGE_CONTENT` — peça o mínimo.

## Instalação e o cargo gerenciado

Ao instalar um bot, o Squord cria em uma operação: o **cargo gerenciado**
(`managedKind: "BOT"`, com as permissões concedidas na instalação, posicionado
abaixo do mais alto de quem instalou), o membro bot e o registro de instalação.
Instalar exige `MANAGE_GUILD`; quem instala só concede o que tem
(`CANNOT_GRANT_PERMISSION`). Permissões de moderação na instalação pedem
confirmação de identidade (step-up) da pessoa.

O token é do bot, rotacionável e revogável — use variável de ambiente
(`SQUORD_BOT_TOKEN`) ou um gerenciador de segredos, nunca no código.
Um `4004` no meio da conexão significa token trocado/revogado ou bot/dono
excluído: o SDK **não** reconecta com o mesmo token — a pessoa dona precisa
fornecer um novo.
