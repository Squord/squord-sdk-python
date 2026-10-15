# Documentação do SDK Python

Guias por assunto, todos alinhados ao contrato real da plataforma
(<https://docs.squord.com.br>):

| Guia | Conteúdo |
|---|---|
| [Gateway, reconexão e retomada](./gateway-e-reconexao.md) | Ciclo de vida do protocolo, heartbeat, zumbi, resume, códigos de fechamento, o que pode ser perdido |
| [Comandos e interações](./comandos-e-interacoes.md) | Texto com prefixo, slash (PUT em bloco), respostas tipadas, botões e menus |
| [Permissões e segurança](./permissoes-e-seguranca.md) | IntFlag, resolução com overwrites, hierarquia, menções seguras, proteções do SDK |
| [Testando seu bot](./testando-seu-bot.md) | MockGateway (protocolo real), MockRest, fixtures, treinando falhas |

O [README](../README.md) traz a visão completa da API pública, do quickstart
aos limites do backend refletidos no SDK. O SDK de Node
([Squord/squord-sdk](https://github.com/Squord/squord-sdk)) segue a mesma
arquitetura, com paridade de contrato.

## Recursos da API mapeados no SDK

| Recurso | Manager | Rotas cobertas |
|---|---|---|
| Bot | `client.bot` | `GET /bots/@me`, `GET /bots/{id}` |
| Usuário | `client.users` | `GET /users/@me` |
| Space | `client.guilds` | `GET /guilds/{id}` |
| Canais e threads | `client.channels` | `GET /channels/{id}`, `GET /guilds/{id}/channels`, threads (criar, listar, post de fórum, thread de mensagem) |
| Mensagens | `client.messages` | enviar, editar, apagar, listar, reagir, fixar |
| Membros | `client.members` | ler, listar (filtros), editar, expulsar, cargos |
| Cargos | `client.roles` | listar |
| Moderação | `client.moderation` | banir, desbanir |
| Comandos | `client.commands` | `GET`/`PUT` global e por Space |
| Interações | `client.interactions` | callback e follow-ups (rotas públicas) |
| Uploads | `client.uploads` | reservar, confirmar e o fluxo completo de 3 passos |

Recursos que a API não expõe a bots (DMs, presença de terceiros, listagem de
bans, voz com E2EE) não aparecem no SDK — não prometemos o que a plataforma
não entrega.
