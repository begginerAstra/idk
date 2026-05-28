import os
import asyncio
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ROBLOX_USERNAMES_URL = "https://users.roblox.com/v1/usernames/users"
ROBLOX_USERS_URL = "https://users.roblox.com/v1/users/{user_id}"
ROBLOX_AVATAR_HEADSHOT_URL = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
ROBLOX_AVATAR_URL = "https://thumbnails.roblox.com/v1/users/avatar"
ROBLOX_FRIENDS_URL = "https://friends.roblox.com/v1/users/{user_id}/friends/count"
ROBLOX_FOLLOWERS_URL = "https://friends.roblox.com/v1/users/{user_id}/followers/count"
ROBLOX_FOLLOWING_URL = "https://friends.roblox.com/v1/users/{user_id}/followings/count"
ROBLOX_GROUPS_URL = "https://groups.roblox.com/v2/users/{user_id}/groups/roles"
ROBLOX_BADGES_URL = "https://badges.roblox.com/v1/users/{user_id}/badges"
ROBLOX_PRESENCE_URL = "https://presence.roblox.com/v1/presence/users"
ROBLOX_INVENTORY_URL = "https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles"
ROBLOX_PROFILE_URL = "https://www.roblox.com/users/{user_id}/profile"

COLOR_OK = 0x2F80ED
COLOR_WARN = 0xF2C94C
COLOR_ERROR = 0xEB5757


def fmt_number(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,}".replace(",", ".")


def account_age(created: str | None) -> str:
    if not created:
        return "N/A"
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return f"{days} dias"
    except Exception:
        return "N/A"


def roblox_time(created: str | None) -> str:
    if not created:
        return "N/A"
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return "N/A"


class RobloxClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def request_json(self, method: str, url: str, **kwargs):
        try:
            async with self.session.request(method, url, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as resp:
                if resp.status in (403, 404):
                    return None
                resp.raise_for_status()
                return await resp.json()
        except Exception:
            return None

    async def resolve_user(self, username: str):
        payload = {"usernames": [username], "excludeBannedUsers": False}
        data = await self.request_json("POST", ROBLOX_USERNAMES_URL, json=payload)
        if not data or not data.get("data"):
            return None
        return data["data"][0]

    async def get_user(self, user_id: int):
        return await self.request_json("GET", ROBLOX_USERS_URL.format(user_id=user_id))

    async def get_count(self, url: str):
        data = await self.request_json("GET", url)
        if not data:
            return None
        return data.get("count")

    async def get_thumbnail(self, user_id: int, avatar: bool = False):
        url = ROBLOX_AVATAR_URL if avatar else ROBLOX_AVATAR_HEADSHOT_URL
        params = {"userIds": str(user_id), "size": "420x420", "format": "Png", "isCircular": "false"}
        data = await self.request_json("GET", url, params=params)
        try:
            return data["data"][0]["imageUrl"]
        except Exception:
            return None

    async def get_groups(self, user_id: int):
        data = await self.request_json("GET", ROBLOX_GROUPS_URL.format(user_id=user_id))
        return data.get("data", []) if data else []

    async def get_badges(self, user_id: int, limit: int = 5):
        params = {"limit": min(limit, 10), "sortOrder": "Desc"}
        data = await self.request_json("GET", ROBLOX_BADGES_URL.format(user_id=user_id), params=params)
        return data.get("data", []) if data else []

    async def get_presence(self, user_id: int):
        data = await self.request_json("POST", ROBLOX_PRESENCE_URL, json={"userIds": [user_id]})
        try:
            return data["userPresences"][0]
        except Exception:
            return None

    async def get_collectibles(self, user_id: int, limit: int = 10):
        params = {"limit": min(limit, 100), "sortOrder": "Desc"}
        data = await self.request_json("GET", ROBLOX_INVENTORY_URL.format(user_id=user_id), params=params)
        return data.get("data", []) if data else []


def presence_text(presence: dict | None) -> str:
    if not presence:
        return "Indisponível"
    kind = presence.get("userPresenceType", 0)
    names = {0: "Offline", 1: "Online", 2: "Em jogo", 3: "No Studio"}
    text = names.get(kind, "Desconhecido")
    game = presence.get("lastLocation")
    if game and kind in (2, 3):
        text += f" — {game}"
    return text


def risk_score(user: dict, followers: int | None, friends: int | None, groups: list, collectibles: list) -> tuple[int, str]:
    score = 100
    created = user.get("created")
    age_days = 0
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass

    if user.get("isBanned"):
        score -= 50
    if age_days and age_days < 30:
        score -= 25
    elif age_days and age_days < 180:
        score -= 10
    if followers is not None and followers < 5:
        score -= 5
    if friends is not None and friends < 10:
        score -= 5
    if len(groups) == 0:
        score -= 5
    if len(collectibles) > 0:
        score += 5

    score = max(0, min(100, score))
    if score >= 80:
        label = "Baixo risco"
    elif score >= 55:
        label = "Risco médio"
    else:
        label = "Alto risco"
    return score, label


class StalkView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.add_item(discord.ui.Button(label="Abrir perfil", url=ROBLOX_PROFILE_URL.format(user_id=user_id)))


class AstraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(headers={"User-Agent": "AstraBot/1.0"})
        await self.tree.sync()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()


bot = AstraBot()


@bot.event
async def on_ready():
    print(f"✅ Logado como {bot.user} | Slash commands sincronizados")


@bot.tree.command(name="stalk", description="Analisa um perfil Roblox com score, status, grupos, badges e limiteds.")
@app_commands.describe(username="Nome de usuário do Roblox")
async def stalk(interaction: discord.Interaction, username: str):
    await interaction.response.defer(thinking=True)

    if not bot.http_session:
        await interaction.followup.send("❌ Sessão HTTP indisponível. Reinicie o bot.", ephemeral=True)
        return

    client = RobloxClient(bot.http_session)
    resolved = await client.resolve_user(username.strip())
    if not resolved:
        embed = discord.Embed(
            title="❌ Usuário não encontrado",
            description=f"Não encontrei nenhum perfil Roblox chamado `{username}`.",
            color=COLOR_ERROR,
        )
        await interaction.followup.send(embed=embed)
        return

    user_id = resolved["id"]
    user, headshot, avatar, friends, followers, following, groups, badges, presence, collectibles = await asyncio.gather(
        client.get_user(user_id),
        client.get_thumbnail(user_id, avatar=False),
        client.get_thumbnail(user_id, avatar=True),
        client.get_count(ROBLOX_FRIENDS_URL.format(user_id=user_id)),
        client.get_count(ROBLOX_FOLLOWERS_URL.format(user_id=user_id)),
        client.get_count(ROBLOX_FOLLOWING_URL.format(user_id=user_id)),
        client.get_groups(user_id),
        client.get_badges(user_id, 5),
        client.get_presence(user_id),
        client.get_collectibles(user_id, 10),
    )

    if not user:
        await interaction.followup.send("❌ Não consegui carregar os dados desse perfil agora.")
        return

    score, label = risk_score(user, followers, friends, groups, collectibles)
    display = user.get("displayName") or resolved.get("displayName") or username
    real_name = user.get("name") or resolved.get("name") or username
    description = user.get("description") or "Sem bio pública."
    if len(description) > 500:
        description = description[:497] + "..."

    embed = discord.Embed(
        title=f"🕵️ Stalk Roblox — {display}",
        url=ROBLOX_PROFILE_URL.format(user_id=user_id),
        description=description,
        color=COLOR_OK if score >= 80 else COLOR_WARN if score >= 55 else COLOR_ERROR,
    )
    embed.set_author(name=f"@{real_name} • ID {user_id}", icon_url=headshot or discord.Embed.Empty)
    if avatar:
        embed.set_image(url=avatar)
    if headshot:
        embed.set_thumbnail(url=headshot)

    embed.add_field(
        name="📌 Conta",
        value=(
            f"Criada em: **{roblox_time(user.get('created'))}**\n"
            f"Idade: **{account_age(user.get('created'))}**\n"
            f"Status: **{'Banida' if user.get('isBanned') else 'Ativa'}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="📊 Social",
        value=(
            f"Amigos: **{fmt_number(friends)}**\n"
            f"Seguidores: **{fmt_number(followers)}**\n"
            f"Seguindo: **{fmt_number(following)}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="🧭 Presença",
        value=f"**{presence_text(presence)}**",
        inline=False,
    )
    embed.add_field(
        name="🛡️ Score de confiança",
        value=f"**{score}/100** — {label}",
        inline=True,
    )
    embed.add_field(
        name="👥 Grupos",
        value=f"**{fmt_number(len(groups))}** grupos encontrados" if groups else "Nenhum grupo público encontrado.",
        inline=True,
    )
    embed.add_field(
        name="💎 Limiteds públicos",
        value=f"**{fmt_number(len(collectibles))}** item(ns) carregados" if collectibles else "Inventário fechado ou sem collectibles públicos.",
        inline=True,
    )

    top_groups = []
    for item in groups[:5]:
        group = item.get("group", {})
        role = item.get("role", {})
        top_groups.append(f"• **{group.get('name', 'Grupo')}** — {role.get('name', 'Membro')}")
    if top_groups:
        embed.add_field(name="🏷️ Principais grupos", value="\n".join(top_groups), inline=False)

    top_badges = []
    for badge in badges[:5]:
        top_badges.append(f"• {badge.get('name', 'Badge')}")
    if top_badges:
        embed.add_field(name="🎖️ Badges recentes", value="\n".join(top_badges), inline=False)

    top_limiteds = []
    for item in collectibles[:5]:
        name = item.get("name") or item.get("assetName") or "Limited"
        rap = item.get("recentAveragePrice")
        top_limiteds.append(f"• **{name}** — RAP: {fmt_number(rap)}")
    if top_limiteds:
        embed.add_field(name="💰 Limiteds vistos", value="\n".join(top_limiteds), inline=False)

    embed.set_footer(text="Astra /stalk • Dados públicos da Roblox")
    await interaction.followup.send(embed=embed, view=StalkView(user_id))


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Defina a variável de ambiente DISCORD_TOKEN no Railway.")
    bot.run(DISCORD_TOKEN)
