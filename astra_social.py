import os
import sqlite3
import random
from datetime import datetime, timezone, date

import discord
from discord import app_commands
from discord.ext import commands

from emojis import e

TOKEN = os.getenv("DISCORD_TOKEN")
BRAND_NAME = os.getenv("BRAND_NAME", "Astra Social")
DB_PATH = os.getenv("DATABASE_PATH", "astra_social.db")
CURRENCY = os.getenv("CURRENCY_NAME", "Astra Coins")
COLOR = 0x8A2BFF

SHOP = {
    "vip": {"name": "Badge VIP", "price": 450, "emoji": e("VIP"), "badge": "VIP"},
    "premium": {"name": "Badge Premium", "price": 850, "emoji": e("PREMIUM"), "badge": "Premium"},
    "coroa": {"name": "Coroa Real", "price": 1200, "emoji": e("COROA"), "badge": "Coroa"},
    "diamante": {"name": "Diamante Azul", "price": 1600, "emoji": e("DIAMANTE"), "badge": "Diamante"},
    "caixa": {"name": "Caixa Misteriosa", "price": 300, "emoji": e("CAIXA"), "badge": None},
}

ITEM_CHOICES = [app_commands.Choice(name=f"{v['emoji']} {v['name']}", value=k) for k, v in SHOP.items()]
RANK_CHOICES = [
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Moedas", value="coins"),
    app_commands.Choice(name="Reputação", value="rep"),
]


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def today() -> str:
    return date.today().isoformat()


def xp_needed(level: int) -> int:
    return 100 + (level - 1) * 50


def bar(xp: int, need: int) -> str:
    filled = min(10, max(0, round((xp / max(need, 1)) * 10)))
    return "█" * filled + "░" * (10 - filled)


def clean(text: str, limit: int) -> str:
    return text.strip().replace("`", "'")[:limit] or "sem bio configurada ainda"


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                bio TEXT NOT NULL DEFAULT 'sem bio configurada ainda',
                coins INTEGER NOT NULL DEFAULT 250,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                rep INTEGER NOT NULL DEFAULT 0,
                badges TEXT NOT NULL DEFAULT '',
                last_daily TEXT,
                last_work INTEGER NOT NULL DEFAULT 0,
                last_rep INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory(
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, item_id)
            )
            """
        )
        self.conn.commit()

    def user(self, member, guild_id: int) -> dict:
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (member.id,)).fetchone()
        if not row:
            self.conn.execute(
                "INSERT INTO users(user_id, guild_id, name, created_at) VALUES(?, ?, ?, ?)",
                (member.id, guild_id, str(member), now_ts()),
            )
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (member.id,)).fetchone()
        user = dict(row)
        user["name"] = str(member)
        if guild_id:
            user["guild_id"] = guild_id
        self.save(user)
        return user

    def save(self, u: dict):
        self.conn.execute(
            """
            UPDATE users SET guild_id=?, name=?, bio=?, coins=?, xp=?, level=?, rep=?, badges=?, last_daily=?, last_work=?, last_rep=?
            WHERE user_id=?
            """,
            (u["guild_id"], u["name"], u["bio"], u["coins"], u["xp"], u["level"], u["rep"], u["badges"], u.get("last_daily"), u.get("last_work", 0), u.get("last_rep", 0), u["user_id"]),
        )
        self.conn.commit()

    def add_item(self, user_id: int, item_id: str):
        self.conn.execute(
            "INSERT INTO inventory(user_id, item_id, quantity) VALUES(?, ?, 1) ON CONFLICT(user_id, item_id) DO UPDATE SET quantity=quantity+1",
            (user_id, item_id),
        )
        self.conn.commit()

    def inv(self, user_id: int):
        return [dict(r) for r in self.conn.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY item_id", (user_id,)).fetchall()]

    def top(self, guild_id: int, mode: str):
        col = "level" if mode == "level" else "coins" if mode == "coins" else "rep"
        return [dict(r) for r in self.conn.execute(f"SELECT * FROM users WHERE guild_id=? ORDER BY {col} DESC, xp DESC LIMIT 10", (guild_id,)).fetchall()]


db = DB(DB_PATH)


def guild_id(interaction: discord.Interaction) -> int:
    return interaction.guild.id if interaction.guild else 0


def add_xp(u: dict, amount: int) -> bool:
    u["xp"] += amount
    leveled = False
    while u["xp"] >= xp_needed(u["level"]):
        u["xp"] -= xp_needed(u["level"])
        u["level"] += 1
        u["coins"] += 75
        leveled = True
    return leveled


def badges_text(u: dict) -> str:
    badges = [b for b in u.get("badges", "").split(",") if b]
    if not badges:
        return f"{e('BADGE')} nenhuma badge ainda"
    out = []
    for b in badges[:8]:
        icon = e("VIP") if b.lower() == "vip" else e("PREMIUM") if b.lower() == "premium" else e("COROA") if b.lower() == "coroa" else e("DIAMANTE") if b.lower() == "diamante" else e("BADGE")
        out.append(f"{icon} {b}")
    return "  ".join(out)


def profile_embed(member, u: dict) -> discord.Embed:
    need = xp_needed(u["level"])
    embed = discord.Embed(
        title=f"{e('PERFIL')} Perfil de {member.display_name}",
        description=(
            f"-# perfil social personalizado da comunidade\n\n"
            f"{e('BIO')} **Bio**\n> {u['bio']}\n\n"
            f"{e('LEVEL')} **Level:** `{u['level']}`\n"
            f"{e('XP')} **XP:** `{bar(u['xp'], need)}` `{u['xp']}/{need}`\n"
            f"{e('MOEDA')} **{CURRENCY}:** `{u['coins']}`\n"
            f"{e('ESTRELA')} **Reputação:** `{u['rep']}`\n\n"
            f"{e('BADGE')} **Badges**\n> {badges_text(u)}"
        ),
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{BRAND_NAME} • demo personalizável")
    return embed


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()


bot = Bot()


@bot.event
async def on_ready():
    print(f"{bot.user} online | {BRAND_NAME}")


@bot.tree.command(name="demo", description="Mostra uma vitrine rápida do Astra Social.")
async def demo(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{e('DIAMANTE')} {BRAND_NAME} — Demo",
        description=(
            f"{e('INFO')} Bot personalizado com a cara da comunidade.\n\n"
            f"{e('PERFIL')} Perfil social\n"
            f"{e('MOEDA')} Economia própria\n"
            f"{e('RANKING')} Ranking\n"
            f"{e('LOJA')} Loja e inventário\n"
            f"{e('BADGE')} Badges exclusivas\n"
            f"{e('ANUNCIO')} Embeds bonitos\n\n"
            f"-# Teste `/perfil`, `/daily`, `/loja`, `/rank` e `/embed-demo`."
        ),
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="template vendável para servidores Discord")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="perfil", description="Mostra seu perfil ou o perfil de outro membro.")
@app_commands.describe(membro="Membro que você quer ver")
async def perfil(interaction: discord.Interaction, membro: discord.Member = None):
    target = membro or interaction.user
    u = db.user(target, guild_id(interaction))
    await interaction.response.send_message(embed=profile_embed(target, u))


@bot.tree.command(name="setbio", description="Configura a bio do seu perfil.")
@app_commands.describe(texto="Sua nova bio")
async def setbio(interaction: discord.Interaction, texto: str):
    u = db.user(interaction.user, guild_id(interaction))
    u["bio"] = clean(texto, 140)
    add_xp(u, 10)
    db.save(u)
    await interaction.response.send_message(f"{e('SUCESSO')} Bio atualizada.", embed=profile_embed(interaction.user, u), ephemeral=True)


@bot.tree.command(name="daily", description="Resgata sua recompensa diária.")
async def daily(interaction: discord.Interaction):
    u = db.user(interaction.user, guild_id(interaction))
    if u.get("last_daily") == today():
        await interaction.response.send_message(f"{e('TEMPO')} Você já pegou o daily hoje.", ephemeral=True)
        return
    reward = random.randint(120, 230)
    u["coins"] += reward
    u["last_daily"] = today()
    leveled = add_xp(u, 25)
    db.save(u)
    msg = f"{e('PRESENTE')} Você recebeu **{reward} {CURRENCY}**."
    if leveled:
        msg += f"\n{e('LEVEL')} Você subiu de level!"
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, u))


@bot.tree.command(name="trabalhar", description="Trabalhe para ganhar moedas e XP.")
async def trabalhar(interaction: discord.Interaction):
    u = db.user(interaction.user, guild_id(interaction))
    current = now_ts()
    remaining = 1200 - (current - int(u.get("last_work", 0)))
    if remaining > 0:
        await interaction.response.send_message(f"{e('TEMPO')} Espere mais **{max(1, remaining // 60)} min**.", ephemeral=True)
        return
    reward = random.randint(60, 140)
    jobs = ["criou um embed bonito", "ajudou a comunidade", "organizou a loja", "participou de um evento", "achou moedas escondidas"]
    u["coins"] += reward
    u["last_work"] = current
    leveled = add_xp(u, 35)
    db.save(u)
    msg = f"{e('TRABALHAR')} Você {random.choice(jobs)} e ganhou **{reward} {CURRENCY}**."
    if leveled:
        msg += f"\n{e('LEVEL')} Level up!"
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, u))


@bot.tree.command(name="rep", description="Dá reputação para alguém.")
@app_commands.describe(membro="Membro que vai receber reputação")
async def rep(interaction: discord.Interaction, membro: discord.Member):
    if membro.id == interaction.user.id:
        await interaction.response.send_message(f"{e('ERRO')} Você não pode dar rep para si mesmo.", ephemeral=True)
        return
    giver = db.user(interaction.user, guild_id(interaction))
    current = now_ts()
    remaining = 43200 - (current - int(giver.get("last_rep", 0)))
    if remaining > 0:
        await interaction.response.send_message(f"{e('TEMPO')} Você poderá dar rep novamente em **{max(1, remaining // 3600)}h**.", ephemeral=True)
        return
    receiver = db.user(membro, guild_id(interaction))
    giver["last_rep"] = current
    receiver["rep"] += 1
    add_xp(giver, 10)
    add_xp(receiver, 15)
    db.save(giver)
    db.save(receiver)
    await interaction.response.send_message(f"{e('ESTRELA')} {interaction.user.mention} deu reputação para {membro.mention}.")


@bot.tree.command(name="loja", description="Mostra a loja da comunidade.")
async def loja(interaction: discord.Interaction):
    embed = discord.Embed(title=f"{e('LOJA')} Loja da Comunidade", description=f"Use `/comprar` com {e('MOEDA')} **{CURRENCY}**.", color=COLOR, timestamp=datetime.now(timezone.utc))
    for item_id, item in SHOP.items():
        embed.add_field(name=f"{item['emoji']} {item['name']} — {item['price']} coins", value=f"ID: `{item_id}`", inline=False)
    embed.set_footer(text=f"{BRAND_NAME} • loja configurável")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="comprar", description="Compra um item da loja.")
@app_commands.describe(item="Item que deseja comprar")
@app_commands.choices(item=ITEM_CHOICES)
async def comprar(interaction: discord.Interaction, item: app_commands.Choice[str]):
    u = db.user(interaction.user, guild_id(interaction))
    data = SHOP[item.value]
    if u["coins"] < data["price"]:
        await interaction.response.send_message(f"{e('ERRO')} Você não tem moedas suficientes.", ephemeral=True)
        return
    u["coins"] -= data["price"]
    if data["badge"]:
        badges = [b for b in u.get("badges", "").split(",") if b]
        if data["badge"] not in badges:
            badges.append(data["badge"])
        u["badges"] = ",".join(badges)
        msg = f"{e('SUCESSO')} Você comprou **{data['name']}**."
    else:
        reward = random.randint(80, 280)
        u["coins"] += reward
        msg = f"{e('CAIXA')} Caixa aberta! Você ganhou **{reward} {CURRENCY}**."
    add_xp(u, 20)
    db.add_item(interaction.user.id, item.value)
    db.save(u)
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, u))


@bot.tree.command(name="inventario", description="Mostra seu inventário.")
async def inventario(interaction: discord.Interaction):
    db.user(interaction.user, guild_id(interaction))
    inv = db.inv(interaction.user.id)
    embed = discord.Embed(title=f"{e('INVENTARIO')} Inventário", color=COLOR, timestamp=datetime.now(timezone.utc))
    if not inv:
        embed.description = f"{e('CAIXA')} Seu inventário está vazio. Use `/loja`."
    else:
        lines = []
        for row in inv:
            item = SHOP.get(row["item_id"])
            if item:
                lines.append(f"{item['emoji']} **{item['name']}** x{row['quantity']}")
        embed.description = "\n".join(lines)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rank", description="Ranking do servidor por level, moedas ou reputação.")
@app_commands.describe(tipo="Tipo de ranking")
@app_commands.choices(tipo=RANK_CHOICES)
async def rank(interaction: discord.Interaction, tipo: str = "level"):
    if not interaction.guild:
        await interaction.response.send_message(f"{e('AVISO')} Ranking funciona melhor dentro de servidor.", ephemeral=True)
        return
    db.user(interaction.user, interaction.guild.id)
    rows = db.top(interaction.guild.id, tipo)
    names = {"level": "Level", "coins": "Moedas", "rep": "Reputação"}
    embed = discord.Embed(title=f"{e('RANKING')} Ranking — {names.get(tipo, 'Level')}", color=COLOR, timestamp=datetime.now(timezone.utc))
    if not rows:
        embed.description = "Ninguém entrou no ranking ainda."
    else:
        medals = [e("COROA"), e("DIAMANTE"), e("ESTRELA")]
        lines = []
        for i, u in enumerate(rows, start=1):
            medal = medals[i - 1] if i <= 3 else f"`#{i}`"
            value = u["level"] if tipo == "level" else u["coins"] if tipo == "coins" else u["rep"]
            lines.append(f"{medal} <@{u['user_id']}> — **{value}**")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"{BRAND_NAME} • ranking personalizável")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="embed-demo", description="Cria um anúncio bonito de demonstração.")
@app_commands.describe(titulo="Título do anúncio", texto="Texto do anúncio")
async def embed_demo(interaction: discord.Interaction, titulo: str = "Evento da Comunidade", texto: str = "Hoje teremos evento valendo recompensas especiais."):
    embed = discord.Embed(
        title=f"{e('ANUNCIO')} {clean(titulo, 80)}",
        description=f"{e('SETA')} {clean(texto, 600)}\n\n{e('PRESENTE')} **Recompensas:** moedas, badges e destaque no ranking\n{e('TEMPO')} **Status:** aberto para participação",
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{BRAND_NAME} • anúncio personalizado")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda", description="Mostra os comandos da demo.")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(title=f"{e('INFO')} Comandos da Demo", description="Teste os principais sistemas do bot personalizável.", color=COLOR)
    embed.add_field(name=f"{e('PERFIL')} Perfil", value="`/perfil` `/setbio` `/rep`", inline=False)
    embed.add_field(name=f"{e('MOEDA')} Economia", value="`/daily` `/trabalhar` `/rank`", inline=False)
    embed.add_field(name=f"{e('LOJA')} Loja", value="`/loja` `/comprar` `/inventario`", inline=False)
    embed.add_field(name=f"{e('ANUNCIO')} Demonstração", value="`/demo` `/embed-demo`", inline=False)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Defina DISCORD_TOKEN no Railway.")
    bot.run(TOKEN)
