# Gateway, reconexão e retomada de sessão

Como o SDK fala o protocolo do gateway do Squord — e o que ele faz quando as
coisas caem. Referência: <https://docs.squord.com.br/gateway/visao-geral>.

## O ciclo de vida, passo a passo

1. **Conexão.** `wss://gateway.squord.com.br/gateway` (o caminho tem de ser
   exatamente `/gateway`).
2. **`hello`.** O servidor envia o intervalo de heartbeat (`heartbeatIntervalMs`,
   hoje 30 s) e um `sessionId` de conexão. O SDK Python usa o valor recebido, nunca um
   número fixo.
3. **`identify`.** Em até 15 s, com o token do bot **sem** o prefixo `Bot`.
   As intents **não** vão no identify: o gateway lê as intents do bot nas
   configurações dele, no momento do identify.
4. **`ready`.** Chegam o `sessionId` (guarde-o), o `userId` da conta do bot e os
   Spaces onde ele está instalado. O SDK Python emite `ready` no cliente.
5. **Heartbeat.** A cada intervalo; o servidor responde `heartbeat.ack`.
   O primeiro heartbeat é espalhado por uma fração aleatória do intervalo,
   para uma reconexão em massa não chegar toda junta.
6. **Eventos.** Frames `event` com `type`, `d` e a sequência `s`, que cresce de
   um em um dentro da sessão. O SDK Python guarda o último `s` processado.

## Quedas e retomada

| Situação | O que o SDK faz |
|---|---|
| Fechamento 4007, 4009, 4000 ou padrão (<4000) | backoff exponencial com jitter (1 s → 60 s) e `resume` com o último `s` |
| `invalid_session` (resume recusado) | `identify` **na mesma conexão** (o prazo de 15 s reinicia) |
| `reconnect` pedido pelo servidor | aguarda o fechamento 4007 e retoma; watchdog fecha se o fechamento não vier |
| 4004 (token inválido/trocado/revogado) | **não** reconecta: emite `error` com orientação e para |
| 4013 (conta suspensa) / 4014 (2 sessões) | **não** reconecta |
| 4001/4002/4005/4012 (erro do bot) | não reconecta até o código ser corrigido |
| Sem `heartbeat.ack` por um intervalo | conexão zumbi: fecha e reconecta com `resume` |

No `resume`, o servidor reenvia os eventos perdidos (`s` de `lastSequence + 1` em
diante) e, **depois deles**, o frame `resumed` com `replayed` e `sequence`.
Não há novo `ready`. Se o histórico guardado (500 eventos) não cobrir a sequência
pedida, o servidor recusa em vez de entregar um histórico furado: o SDK recebe
`invalid_session` e começa uma sessão nova.

```python
@client.on("resumed")
async def on_resumed(info):
    print(f"Sessão retomada: {info['replayed']} eventos recuperados")
```

## O que pode ser perdido

O SDK Python não inventa garantia que o backend não dá:

- A retomada vale por **120 segundos** após a queda; depois, nova sessão.
- O replay cobre até **500 eventos**. Queda longa = eventos perdidos.
- Eventos desconhecidos (criados no futuro) chegam em `unknownEvent` —
  seu bot não quebra.
- Para reconciliar estado após uma queda longa, use o REST:
  histórico de mensagens (`client.messages.list`), membros (`client.members.list`),
  canais (`client.channels.fetchTree`).

## Deduplicação

Cada evento durável traz `s` crescente. O SDK Python descarta frames com `s` menor ou
igual ao último processado (replays de borda, reconexões rápidas), expondo
`gateway.eventsReceived` (bruto) e `gateway.eventsDropped` (descartados) para
diagnóstico.

## Presença

```ts
client.setPresence({ status: "IDLE", customStatus: "Tocando no Lounge" });
// status: ONLINE | IDLE | DND | INVISIBLE; customStatus até 128 caracteres
```

Enquanto houver conexão aberta, o bot aparece online nos Spaces onde está
instalado; o último status escolhido vale nas próximas conexões.

## Sessões

Um bot mantém até **2 sessões simultâneas** — a terceira recebe `4014` antes de
ser atendida. Cada IP pode ter até 64 conexões; o gateway limita frames enviados
a 120/min (600 antes do identify). O SDK Python só envia `identify`, `resume`,
`heartbeat` e `presence.update`, bem abaixo do teto.
