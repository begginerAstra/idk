import os
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
TICKET_PREFIX = os.getenv("TICKET_PREFIX", "ticket")
BRAND_NAME = os.getenv("BRAND_NAME", "Astra Support")

COLOR_MAIN = 0x2F80ED
COLOR_SUCCESS = 0x27AE60
COLOR_WARN = 0xF2C94C
COLOR_ERROR = 0xEB5757


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_dt(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M UTC")


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
        return True
    if STAFF_ROLE_ID:
        return any(role.id == STAFF_ROLE_ID for role in member.roles)
    return False


def ticket_topic(user_id: int) -> str:
    return f"ticket_owner={user_id}"


def get_ticket_owner_id(channel: discord.TextChannel) -> int | None:
    if not channel.topic:
        return None
    for part in channel.topic.split():
        if part.startswith("ticket_owner="):
            raw = part.replace("ticket_owner=", "").strip()
            if raw.isdigit():
                return int(raw)
    return None


async def send_log(guild: discord.Guild, embed: discord.Embed, file: discord.File | None = None):
    if not LOG_CHANNEL_ID:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed, file=file)
        except discord.HTTPException:
            pass


async def create_transcript(channel: discord.TextChannel) -> discord.File:
    lines: list[str] = []
    lines.append(f"Transcript do canal: #{channel.name}")
    lines.append(f"Canal ID: {channel.id}")
    lines.append(f"Gerado em: {format_dt(utc_now())}")
    lines.append("=" * 60)

    async for message in channel.history(limit=None, oldest_first=True):
        created = message.created_at.strftime("%d/%m/%Y %H:%M:%S UTC")
        author = f"{message.author} ({message.author.id})"
        content = message.content or ""
        if message.attachments:
            attachment_urls = " | ".join(att.url for att in message.attachments)
            content += f"\n[ANEXOS] {attachment_urls}"
        if message.embeds:
            content += f"\n[EMBEDS] {len(message.embeds)} embed(s)"
        lines.append(f"[{created}] {author}: {content}")

    data = "\n".join(lines).encode("utf-8")
    buffer = io.BytesIO(data)
    filename = f"transcript-{channel.name}-{int(utc_now().timestamp())}.txt"
    return discord.File(buffer, filename=filename)


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Esse botão só funciona dentro de um servidor.", ephemeral=True)
            return

        guild = interaction.guild
        member = interaction.user

        for channel in guild.text_channels:
            if get_ticket_owner_id(channel) == member.id:
                await interaction.response.send_message(f"⚠️ Você já tem um ticket aberto: {channel.mention}", ephemeral=True)
                return

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True, attach_files=True, embed_links=True),
        }

        staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True)

        safe_name = member.name.lower().replace(" ", "-")[:24]
        channel_name = f"{TICKET_PREFIX}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=ticket_topic(member.id),
                reason=f"Ticket aberto por {member} ({member.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não tenho permissão para criar canais. Me dê `Manage Channels`.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Ticket aberto",
            description=(
                f"Olá {member.mention}, explique seu problema com o máximo de detalhes.\n\n"
                "Nossa equipe vai te responder assim que possível."
            ),
            color=COLOR_MAIN,
            timestamp=utc_now(),
        )
        embed.add_field(name="Usuário", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="Status", value="🟢 Aberto", inline=True)
        embed.set_footer(text=BRAND_NAME)

        await channel.send(content=f"{member.mention} {staff_role.mention if staff_role else ''}", embed=embed, view=TicketManageView())
        await interaction.response.send_message(f"✅ Ticket criado: {channel.mention}", ephemeral=True)

        log_embed = discord.Embed(title="🎫 Ticket criado", color=COLOR_SUCCESS, timestamp=utc_now())
        log_embed.add_field(name="Usuário", value=f"{member.mention} (`{member.id}`)", inline=False)
        log_embed.add_field(name="Canal", value=channel.mention, inline=False)
        await send_log(guild, log_embed)


class TicketManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Assumir", emoji="🙋", style=discord.ButtonStyle.secondary, custom_id="ticket:claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Apenas staff pode assumir tickets.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🙋 Ticket assumido",
            description=f"Este ticket foi assumido por {interaction.user.mention}.",
            color=COLOR_MAIN,
            timestamp=utc_now(),
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return

        channel = interaction.channel
        owner_id = get_ticket_owner_id(channel)
        allowed = is_staff(interaction.user) or interaction.user.id == owner_id
        if not allowed:
            await interaction.response.send_message("❌ Você não pode fechar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("⚠️ Tem certeza que deseja fechar este ticket?", view=TicketConfirmCloseView(), ephemeral=True)


class TicketConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmar fechamento", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return

        channel = interaction.channel
        owner_id = get_ticket_owner_id(channel)
        allowed = is_staff(interaction.user) or interaction.user.id == owner_id
        if not allowed:
            await interaction.response.send_message("❌ Você não pode fechar este ticket.", ephemeral=True)
            return

        await interaction.response.edit_message(content="🔒 Fechando ticket e gerando transcript...", view=None)

        transcript = await create_transcript(channel)
        log_embed = discord.Embed(title="🔒 Ticket fechado", color=COLOR_WARN, timestamp=utc_now())
        log_embed.add_field(name="Canal", value=f"#{channel.name}\n`{channel.id}`", inline=False)
        log_embed.add_field(name="Fechado por", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
        if owner_id:
            log_embed.add_field(name="Dono do ticket", value=f"<@{owner_id}>\n`{owner_id}`", inline=True)
        log_embed.set_footer(text=BRAND_NAME)

        await send_log(interaction.guild, log_embed, transcript)

        try:
            await channel.send("🔒 Ticket fechado. Este canal será deletado em alguns segundos.")
        except discord.HTTPException:
            pass
        await channel.delete(reason=f"Ticket fechado por {interaction.user} ({interaction.user.id})")

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Fechamento cancelado.", view=None)


class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketOpenView())
        self.add_view(TicketManageView())
        await self.tree.sync()


bot = TicketBot()


@bot.event
async def on_ready():
    print(f"✅ {bot.user} online | Sistema de tickets carregado")


@bot.tree.command(name="ticket-panel", description="Envia o painel profissional de tickets neste canal.")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"🎫 {BRAND_NAME}",
        description=(
            "Precisa de ajuda? Clique no botão abaixo para abrir um ticket privado.\n\n"
            "**Use para:**\n"
            "• Suporte\n"
            "• Compras\n"
            "• Dúvidas\n"
            "• Denúncias\n\n"
            "Evite abrir tickets sem necessidade."
        ),
        color=COLOR_MAIN,
        timestamp=utc_now(),
    )
    embed.set_footer(text="Sistema profissional de tickets")
    await interaction.response.send_message(embed=embed, view=TicketOpenView())


@ticket_panel.error
async def ticket_panel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Você precisa da permissão `Manage Server` para usar este comando.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Ocorreu um erro ao criar o painel.", ephemeral=True)


@bot.tree.command(name="ticket-add", description="Adiciona um usuário ao ticket atual.")
@app_commands.describe(user="Usuário que será adicionado ao ticket")
async def ticket_add(interaction: discord.Interaction, user: discord.Member):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
        return
    if not is_staff(interaction.user):
        await interaction.response.send_message("❌ Apenas staff pode adicionar usuários ao ticket.", ephemeral=True)
        return
    if get_ticket_owner_id(interaction.channel) is None:
        await interaction.response.send_message("❌ Use este comando dentro de um canal de ticket.", ephemeral=True)
        return

    await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
    await interaction.response.send_message(f"✅ {user.mention} foi adicionado ao ticket.")


@bot.tree.command(name="ticket-remove", description="Remove um usuário do ticket atual.")
@app_commands.describe(user="Usuário que será removido do ticket")
async def ticket_remove(interaction: discord.Interaction, user: discord.Member):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
        return
    if not is_staff(interaction.user):
        await interaction.response.send_message("❌ Apenas staff pode remover usuários do ticket.", ephemeral=True)
        return
    if get_ticket_owner_id(interaction.channel) is None:
        await interaction.response.send_message("❌ Use este comando dentro de um canal de ticket.", ephemeral=True)
        return

    await interaction.channel.set_permissions(user, overwrite=None)
    await interaction.response.send_message(f"✅ {user.mention} foi removido do ticket.")


@bot.tree.command(name="ticket-rename", description="Renomeia o ticket atual.")
@app_commands.describe(name="Novo nome do canal, sem espaços")
async def ticket_rename(interaction: discord.Interaction, name: str):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
        return
    if not is_staff(interaction.user):
        await interaction.response.send_message("❌ Apenas staff pode renomear tickets.", ephemeral=True)
        return
    if get_ticket_owner_id(interaction.channel) is None:
        await interaction.response.send_message("❌ Use este comando dentro de um canal de ticket.", ephemeral=True)
        return

    clean = name.lower().replace(" ", "-")[:80]
    await interaction.channel.edit(name=clean, reason=f"Ticket renomeado por {interaction.user}")
    await interaction.response.send_message(f"✅ Ticket renomeado para `{clean}`.")


@bot.tree.command(name="ticket-close", description="Fecha o ticket atual com transcript.")
async def ticket_close(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
        return
    owner_id = get_ticket_owner_id(interaction.channel)
    if owner_id is None:
        await interaction.response.send_message("❌ Use este comando dentro de um canal de ticket.", ephemeral=True)
        return
    if not (is_staff(interaction.user) or interaction.user.id == owner_id):
        await interaction.response.send_message("❌ Você não pode fechar este ticket.", ephemeral=True)
        return
    await interaction.response.send_message("⚠️ Tem certeza que deseja fechar este ticket?", view=TicketConfirmCloseView(), ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Defina a variável DISCORD_TOKEN no Railway.")
    bot.run(DISCORD_TOKEN)
