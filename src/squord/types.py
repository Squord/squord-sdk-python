"""Tipos dos payloads reais da API REST e do gateway do Squord (v1).

Espelham o contrato publicado em https://docs.squord.com.br (OpenAPI).
Os dicionários trafegam em JSON UTF-8 com campos em ``camelCase``; como a
API admite campos ausentes, os ``TypedDict`` são declarados com
``total=False`` — trate os campos como opcionais e consulte a referência.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .enums import (
    AttachmentScanStatus,
    ButtonStyle,
    ChannelType,
    CommandOptionType,
    InteractionCallbackType,
    InteractionType,
    MemberType,
    MessageType,
    PresenceStatus,
    RoleManagedKind,
    ThreadAutoArchiveMinutes,
    UploadStatus,
)

Snowflake = str
ISODate = str
PermissionBits = str
Cursor = str
Nonce = str


# ------------------------------------------------------------------ --
# Primitivos
# ---------------------------------------------------------------------


class AllowedMentions(TypedDict, total=False):
    """Menções permitidas em uma mensagem. Seguras por padrão."""

    users: bool
    roles: bool
    everyone: bool


class Page(TypedDict, total=False):
    """Formato de página devolvido pelas rotas paginadas por cursor."""

    items: list[Any]
    prevCursor: str | None
    nextCursor: str | None
    hasMore: bool


class CursorPaginationParams(TypedDict, total=False):
    limit: int
    before: Cursor
    after: Cursor


# ------------------------------------------------------------------ --
# Usuários, membros, cargos
# ---------------------------------------------------------------------


class APIUser(TypedDict, total=False):
    id: Snowflake
    username: str
    displayName: str
    avatarUrl: str | None
    avatarAnimatedUrl: str | None
    nameStyle: dict[str, Any] | None
    flags: int
    deleted: bool
    suspended: bool
    premium: bool


class APIMember(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake
    userId: Snowflake
    user: APIUser
    type: MemberType
    nickname: str | None
    avatarUrl: str | None
    avatarAnimatedUrl: str | None
    bannerUrl: str | None
    bannerAnimatedUrl: str | None
    bio: str | None
    bioEmojis: list[dict[str, Any]]
    nameStyle: dict[str, Any] | None
    profileFont: str | None
    profileTheme: list[str] | None
    roleIds: list[Snowflake]
    joinedAt: ISODate
    timeoutUntil: ISODate | None
    deaf: bool
    mute: bool
    pending: bool
    boostingSince: ISODate | None
    createdAt: ISODate
    updatedAt: ISODate


class APIMemberPage(TypedDict, total=False):
    items: list[APIMember]
    prevCursor: str | None
    nextCursor: str | None
    hasMore: bool


class APIRole(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake
    name: str
    color: str | None
    position: int
    permissions: PermissionBits
    hoist: bool
    mentionable: bool
    managed: bool
    managedKind: RoleManagedKind | None
    botId: Snowflake | None
    icon: str | None
    selfAssignable: bool
    createdAt: ISODate
    updatedAt: ISODate


class APIChannelOverwrite(TypedDict, total=False):
    targetId: Snowflake
    targetType: str
    allow: PermissionBits
    deny: PermissionBits


class APIForumTag(TypedDict, total=False):
    id: Snowflake
    name: str
    emoji: str | None
    moderated: bool


class APIChannel(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake
    categoryId: Snowflake | None
    name: str
    type: ChannelType
    position: int
    topic: str | None
    topicUpdatedAt: ISODate | None
    topicUpdatedById: Snowflake | None
    isPrivate: bool
    rateLimitPerUser: int
    bitrate: int | None
    userLimit: int | None
    chatEnabled: bool
    lastMessageId: Snowflake | None
    overwrites: list[APIChannelOverwrite]
    availableTags: list[APIForumTag]
    requireTag: bool
    defaultAutoArchiveMinutes: ThreadAutoArchiveMinutes | None
    createdAt: ISODate
    updatedAt: ISODate


class APIThreadPostPreview(TypedDict, total=False):
    messageId: Snowflake
    author: APIUser
    content: str
    hasAttachment: bool
    hasImage: bool
    hasSticker: bool
    deleted: bool
    moderated: bool


class APIThread(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake
    type: str
    parentId: Snowflake
    name: str
    ownerId: Snowflake
    starterMessageId: Snowflake | None
    isForumPost: bool
    archived: bool
    archivedAt: ISODate | None
    locked: bool
    autoArchiveMinutes: ThreadAutoArchiveMinutes
    rateLimitPerUser: int
    messageCount: int
    lastMessageId: Snowflake | None
    lastMessageAt: ISODate
    appliedTagIds: list[Snowflake]
    postPreview: APIThreadPostPreview | None
    createdAt: ISODate
    updatedAt: ISODate


class APIThreadPage(TypedDict, total=False):
    items: list[APIThread]
    prevCursor: str | None
    nextCursor: str | None
    hasMore: bool


class APIChannelTreeNode(TypedDict, total=False):
    category: APIChannel | None
    channels: list[APIChannel]


class APIGuildRule(TypedDict, total=False):
    title: str
    description: str


class APIGuildSelf(TypedDict, total=False):
    memberId: Snowflake
    roleIds: list[Snowflake]
    permissions: PermissionBits
    isOwner: bool


class APIGuild(TypedDict, total=False):
    id: Snowflake
    ownerId: Snowflake
    name: str
    slug: str
    description: str | None
    iconUrl: str | None
    iconAnimatedUrl: str | None
    bannerUrl: str | None
    bannerAnimatedUrl: str | None
    bannerPlaceholder: str | None
    defaultChannelId: Snowflake | None
    systemChannelId: Snowflake | None
    visibility: str
    verificationLevel: str
    accessMode: str
    requireVerifiedEmail: bool
    requireTwoFactor: bool
    moderationMfaRequired: bool
    joinRequestRoleIds: list[Snowflake]
    requireJoinMessage: bool
    joinRequestRetryDays: int
    memberCount: int
    flags: int
    planId: str
    vanityLapsesAt: ISODate | None
    vanityInvite: bool
    boostCount: int
    boostLevel: int
    boostMessages: bool
    discoveryCategory: str | None
    locale: str | None
    rules: list[APIGuildRule]
    rulesUpdatedAt: ISODate | None
    discoverable: bool
    discoverableSince: ISODate | None
    minAccountAgeDays: int
    createdAt: ISODate
    updatedAt: ISODate
    self: APIGuildSelf


class APIBot(TypedDict, total=False):
    id: Snowflake
    user: APIUser
    description: str | None
    ownerUsername: str
    public: bool
    verified: bool
    installCount: int
    termsUrl: str | None
    privacyUrl: str | None
    createdAt: ISODate
    intents: int


# ------------------------------------------------------------------ --
# Mensagens
# ---------------------------------------------------------------------


class APIAttachment(TypedDict, total=False):
    id: Snowflake
    kind: str
    source: str
    providerId: str | None
    filename: str
    contentType: str
    size: int
    url: str
    thumbnailUrl: str | None
    width: int | None
    height: int | None
    durationMs: int | None
    placeholder: str | None
    scanStatus: AttachmentScanStatus


class APIEmbed(TypedDict, total=False):
    type: str
    url: str | None
    title: str | None
    description: str | None
    siteName: str | None
    thumbnailUrl: str | None
    color: str | None
    author: dict[str, Any] | None
    fields: list[dict[str, Any]]
    image: dict[str, Any] | None
    footer: dict[str, Any] | None
    timestamp: ISODate | None
    video: dict[str, Any] | None


class APIEmbedInput(TypedDict, total=False):
    """Embed que se envia (formato aceito pelo Squord)."""

    title: str | None
    description: str | None
    url: str | None
    color: int | str | None
    timestamp: str | None
    author: dict[str, Any] | None
    footer: dict[str, Any] | None
    image: dict[str, Any] | None
    thumbnail: dict[str, Any] | None
    fields: list[dict[str, Any]]


class APIReaction(TypedDict, total=False):
    emoji: str
    count: int
    userIds: list[Snowflake]
    me: bool


class APIMessageMentions(TypedDict, total=False):
    userIds: list[Snowflake]
    roleIds: list[Snowflake]
    channelIds: list[Snowflake]
    everyone: bool


class APIMessageReplyTo(TypedDict, total=False):
    id: Snowflake
    authorId: Snowflake
    author: APIUser
    content: str
    deleted: bool
    moderated: bool
    preview: dict[str, Any]


class APIMessage(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake | None
    channelId: Snowflake
    authorId: Snowflake
    type: MessageType
    content: str
    replyToId: Snowflake | None
    attachments: list[APIAttachment]
    embeds: list[APIEmbed]
    components: list[dict[str, Any]]
    interaction: dict[str, Any] | None
    mentions: APIMessageMentions
    reactions: list[APIReaction]
    pinned: bool
    editedAt: ISODate | None
    deletedAt: ISODate | None
    moderated: bool
    nonce: Nonce | None
    call: dict[str, Any] | None
    poll: dict[str, Any] | None
    forward: dict[str, Any] | None
    relay: dict[str, Any] | None
    relayedCount: int | None
    stickers: list[dict[str, Any]]
    emojis: list[dict[str, Any]]
    thread: dict[str, Any] | None
    automod: dict[str, Any] | None
    createdAt: ISODate
    updatedAt: ISODate
    author: APIUser
    memberNickname: str | None
    memberAvatarUrl: str | None
    memberNameStyle: dict[str, Any] | None
    replyTo: APIMessageReplyTo | None


class APIMessagePage(TypedDict, total=False):
    items: list[APIMessage]
    prevCursor: str | None
    nextCursor: str | None
    hasMore: bool


class APIMessageCreateBody(TypedDict, total=False):
    content: str
    embeds: list[APIEmbedInput]
    components: list[dict[str, Any]]
    allowedMentions: AllowedMentions
    replyToId: Snowflake | None
    attachmentIds: list[Snowflake]
    nonce: Nonce | None


class APIMessageEditBody(TypedDict, total=False):
    content: str
    embeds: list[APIEmbedInput]
    components: list[dict[str, Any]]
    allowedMentions: AllowedMentions


# ------------------------------------------------------------------ --
# Componentes
# ---------------------------------------------------------------------


class APIButton(TypedDict, total=False):
    type: str
    style: ButtonStyle
    label: str
    customId: str
    url: str
    disabled: bool


class APISelectOption(TypedDict, total=False):
    label: str
    value: str
    description: str


class APISelectMenu(TypedDict, total=False):
    type: str
    customId: str
    placeholder: str
    minValues: int
    maxValues: int
    disabled: bool
    options: list[APISelectOption]


class APIComponentRow(TypedDict, total=False):
    type: str
    components: list[dict[str, Any]]


# ------------------------------------------------------------------ --
# Comandos e interações
# ---------------------------------------------------------------------


class APICommandOptionChoice(TypedDict, total=False):
    name: str
    value: str | int


class APICommandOption(TypedDict, total=False):
    type: CommandOptionType
    name: str
    description: str
    required: bool
    choices: list[APICommandOptionChoice]


class APICommand(TypedDict, total=False):
    id: Snowflake
    botId: Snowflake
    guildId: Snowflake | None
    name: str
    description: str
    options: list[APICommandOption]
    updatedAt: ISODate


class APICommandInput(TypedDict, total=False):
    name: str
    description: str
    options: list[APICommandOption]


class APIInteractionCommandData(TypedDict, total=False):
    id: Snowflake
    name: str
    options: list[dict[str, Any]]


class APIInteractionComponentData(TypedDict, total=False):
    messageId: Snowflake
    customId: str
    type: str
    values: list[str]


class APIInteraction(TypedDict, total=False):
    id: Snowflake
    token: str
    type: InteractionType
    guildId: Snowflake
    channelId: Snowflake
    user: APIUser
    member: APIMember | None
    command: APIInteractionCommandData
    component: APIInteractionComponentData
    createdAt: ISODate


class APIInteractionReplyData(TypedDict, total=False):
    content: str
    embeds: list[APIEmbedInput]
    components: list[dict[str, Any]]
    allowedMentions: AllowedMentions
    ephemeral: bool


class APIInteractionCallbackBody(TypedDict, total=False):
    type: InteractionCallbackType
    data: APIInteractionReplyData


# ------------------------------------------------------------------ --
# Uploads
# ---------------------------------------------------------------------


class APIUpload(TypedDict, total=False):
    id: Snowflake
    scope: str
    filename: str
    contentType: str
    size: int
    status: UploadStatus
    url: str | None
    thumbnailUrl: str | None
    guildId: Snowflake | None
    storageKey: str
    scanStatus: str
    animated: bool
    animatedUrl: str | None
    createdAt: ISODate
    expiresAt: ISODate


class APIUploadTarget(TypedDict, total=False):
    uploadUrl: str
    method: str
    headers: dict[str, str]
    storageKey: str
    publicUrl: str
    expiresAt: ISODate


class APIUploadReservation(TypedDict, total=False):
    upload: APIUpload
    target: APIUploadTarget


class APIUploadCreateBody(TypedDict, total=False):
    scope: str
    filename: str
    contentType: str
    size: int
    guildId: Snowflake | None


class APIUploadConfirmBody(TypedDict, total=False):
    crop: dict[str, int] | None
    placeholder: str | None


# ------------------------------------------------------------------ --
# Moderação
# ---------------------------------------------------------------------


class APIMemberEditBody(TypedDict, total=False):
    nickname: str | None
    roleIds: list[Snowflake]
    timeoutUntil: ISODate | None
    deaf: bool
    mute: bool


class APIMemberBanBody(TypedDict, total=False):
    reason: str | None
    deleteMessageSeconds: int


class APIMemberBan(TypedDict, total=False):
    id: Snowflake
    guildId: Snowflake
    userId: Snowflake
    moderatorId: Snowflake
    byPlatform: bool
    reason: str | None
    createdAt: ISODate


# ------------------------------------------------------------------ --
# Erros
# ---------------------------------------------------------------------


class APIErrorBody(TypedDict, total=False):
    statusCode: int
    code: str
    message: str
    details: Any
    requestId: str


class APIRateLimitDetails(TypedDict, total=False):
    bucket: str
    retryAfter: int


# ------------------------------------------------------------------ --
# Gateway — frames
# ---------------------------------------------------------------------


class GatewayHello(TypedDict, total=False):
    heartbeatIntervalMs: int
    sessionId: str
    protocolVersion: int


class GatewayIdentify(TypedDict, total=False):
    token: str
    protocolVersion: int
    guildIds: list[str]
    capabilities: list[str]


class GatewayResume(TypedDict, total=False):
    token: str
    sessionId: str
    lastSequence: int


class ReadyGuild(TypedDict, total=False):
    id: Snowflake
    name: str
    iconUrl: str | None


class GatewayReady(TypedDict, total=False):
    sessionId: str
    userId: Snowflake
    guilds: list[ReadyGuild]
    resumeGatewayUrl: str


class GatewayResumed(TypedDict, total=False):
    sessionId: str
    replayed: int
    sequence: int


class GatewayInvalidSession(TypedDict, total=False):
    resumable: bool


class GatewayReconnect(TypedDict, total=False):
    reason: str
    resumable: bool


class GatewayErrorFrame(TypedDict, total=False):
    code: str
    message: str
    details: Any


class GatewayPresenceUpdate(TypedDict, total=False):
    status: PresenceStatus
    customStatus: str | None
    afk: bool


# ------------------------------------------------------------------ --
# Gateway — payloads de eventos
# ---------------------------------------------------------------------


class MessageDeletedPayload(TypedDict, total=False):
    messageId: Snowflake
    channelId: Snowflake
    guildId: Snowflake | None
    lastMessageId: Snowflake | None


class MessageBulkDeletedPayload(TypedDict, total=False):
    messageIds: list[Snowflake]
    channelId: Snowflake
    guildId: Snowflake | None
    lastMessageId: Snowflake | None


class PollVotePayload(TypedDict, total=False):
    messageId: Snowflake
    channelId: Snowflake
    guildId: Snowflake | None
    userId: Snowflake
    results: dict[str, Any]


class ReactionAddedPayload(TypedDict, total=False):
    messageId: Snowflake
    channelId: Snowflake
    guildId: Snowflake | None
    userId: Snowflake
    reaction: dict[str, Any]
    customEmoji: dict[str, Any] | None


class ReactionRemovedPayload(TypedDict, total=False):
    messageId: Snowflake
    channelId: Snowflake
    guildId: Snowflake | None
    userId: Snowflake
    emoji: str


class MemberJoinedPayload(TypedDict, total=False):
    guildId: Snowflake
    member: APIMember


class MemberUpdatedPayload(TypedDict, total=False):
    guildId: Snowflake
    member: APIMember


class MemberLeftPayload(TypedDict, total=False):
    guildId: Snowflake
    userId: Snowflake


class MemberBannedPayload(TypedDict, total=False):
    guildId: Snowflake
    userId: Snowflake
    reason: str | None


class MemberUnbannedPayload(TypedDict, total=False):
    guildId: Snowflake
    userId: Snowflake


class GuildDeletedPayload(TypedDict, total=False):
    guildId: Snowflake


class GuildTakenDownPayload(TypedDict, total=False):
    guildId: Snowflake
    name: str


class GuildBoostPayload(TypedDict, total=False):
    guildId: Snowflake
    userId: Snowflake
    boostIds: list[Snowflake]
    boostCount: int
    boostLevel: int
    previousLevel: int
    reason: str


class ChannelDeletedPayload(TypedDict, total=False):
    channelId: Snowflake
    guildId: Snowflake


class ChannelTreeInvalidatedPayload(TypedDict, total=False):
    guildId: Snowflake


class RoleDeletedPayload(TypedDict, total=False):
    roleId: Snowflake
    guildId: Snowflake


class ThreadDeletedPayload(TypedDict, total=False):
    threadId: Snowflake
    parentId: Snowflake
    guildId: Snowflake


class EmojiDeletedPayload(TypedDict, total=False):
    emojiId: Snowflake
    guildId: Snowflake


class StickerDeletedPayload(TypedDict, total=False):
    stickerId: Snowflake
    guildId: Snowflake


class GuildEventDeletedPayload(TypedDict, total=False):
    eventId: Snowflake
    guildId: Snowflake


class AnnouncementFollowDeletedPayload(TypedDict, total=False):
    followId: Snowflake
    sourceChannelId: Snowflake
    targetChannelId: Snowflake


class VoiceStateUpdatedPayload(TypedDict, total=False):
    state: dict[str, Any] | None
    userId: Snowflake
    channelId: Snowflake


class VoiceRoomUpdatedPayload(TypedDict, total=False):
    room: dict[str, Any]


class VoiceMemberMovedPayload(TypedDict, total=False):
    userId: Snowflake
    guildId: Snowflake
    fromChannelId: Snowflake
    toChannelId: Snowflake
    state: dict[str, Any]


class VoiceBotKeyRequestedPayload(TypedDict, total=False):
    channelId: Snowflake
    recipients: list[dict[str, Any]]


class ApplicationCommandUpdatedPayload(TypedDict, total=False):
    guildId: Snowflake
    botId: Snowflake


# ------------------------------------------------------------------ --
# Menções (formatação de conteúdo)
# ---------------------------------------------------------------------


def user_mention(user_id: Snowflake) -> str:
    """Menção de pessoa: ``<@ID>``."""
    return f"<@{user_id}>"


def role_mention(role_id: Snowflake) -> str:
    """Menção de cargo: ``<@&ID>``."""
    return f"<@&{role_id}>"


def channel_mention(channel_id: Snowflake) -> str:
    """Menção de canal: ``<#ID>``."""
    return f"<#{channel_id}>"
