import os
import sqlite3
import random
from datetime import datetime, timezone, date

import discord
from discord import app_commands
from discord.ext import commands

from emojis import e

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BRAND_NAME = os.getenv("BRAND_NAME", "Astra Social")
DATABASE_PATH = os.getenv("DATABASE_PATH", "astra_social.db")
CURRENCY_NAME = os.getenv("CURRENCY_NAME", "Astra Coins")

COLOR_MAIN = 0x8A2BFF
COLOR_OK = 0x2ECC71
COLOR_WARN = 0xF1C40F
COLOR_ERROR = 0xE74C3C

SHOP_ITEMS = {
    "vip_badge": {
        "name": "Badge VIP",
        "price": 450,
        "emoji": e("VIP"),
        "type": "badge",
        "badge": "VIP",
        "desc": "Badge visual para o perfil.",
    },
    "premium_badge": {
        "name": "Badge Premium",
        "price": 850,
        "emoji": e("PREMIUM"),
        "type": "badge",
        "badge": "Premium",
        "desc": "Badge premium para destacar o perfil.",
    },
    "coroa": {
        "name": "Coroa Real",
        "price": 1200,
        "emoji": e("COROA"),
        "type": "badge",
        "badge": "Coroa",
        "desc": "Badge rara para membros importantes.",
    },
    "diamante": {
        "name": "Diamante Azul",
        "price": 1600,
        "emoji": e("DIAMANTE"),
        "type": "badge",
        "badge": "Diamante",
        "desc": "Badge lendária para perfis chamativos.",
    },
    "caixa": {
        "name": "Caixa Misteriosa",
        "price": 300,
        "emoji": e("CAIXA"),
        "type": "box",
        "desc": "Abre e ganha moedas ou XP aleatório.",
    },
}

ITEM_CHOICES = [
    app_commands.Choice(name=f"{item['emoji']} {item['name']}", value=item_id)
    for item_id, item in SHOP_ITEMS.items()
]

RANK_CHOICES = [
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Moedas", value="coins"),
    app_commands.Choice(name="Reputação", value="rep"),
]


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def today_key() -> str:
    return date.today().isoformat()


def progress_bar(current: int, needed: int) -> str:
    if needed <= 0:
        return "██████████"
    filled = min(10, max(0, round((current / needed) * 10)))
    return "█" * filled + "░" * (10 - filled)


def xp_needed(level: int) -> int:
    return 100 + (level - 1) * 50


def clean_text(text: str, limit: int = 120) -> str:
    text = text.strip().replace("`", "'")
    return text[:limit] if text else ""


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                bio TEXT NOT NULL DEFAULT 'sem bio configurada ainda',
                coins INTEGER NOT NULL DEFAULT 250,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                rep INTEGER NOT NULL DEFAULT 0,
                badges TEXT NOT NULL DEFAULT '',
                banner TEXT NOT NULL DEFAULT 'default_dark',
                color TEXT NOT NULL DEFAULT '#8A2BFF',
                last_daily TEXT,
                last_work INTEGER NOT NULL DEFAULT 0,
                last_rep INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_id)
            )
            """
        )
        self.conn.commit()

    def get_user(self, user_id: int, guild_id: int, name: str):
        row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return dict(row)
        self.conn.execute(
            """
            INSERT INTO users (user_id, guild_id, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, guild_id, name, now_ts()),
        )
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())

    def save_user(self, user: dict):
        self.conn.execute(
            """
            UPDATE users
            SET guild_id=?, name=?, bio=?, coins=?, xp=?, level=?, rep=?, badges=?, banner=?, color=?, last_daily=?, last_work=?, last_rep=?
            WHERE user_id=?
            """,
            (
                user["guild_id"],
                user["name"],
                user["bio"],
                user["coins"],
                user["xp"],
                user["level"],
                user["rep"],
                user["badges"],
                user["banner"],
                user["color"],
                user.get("last_daily"),
                user.get("last_work", 0),
                user.get("last_rep", 0),
                user["user_id"],
            ),
        )
        self.conn.commit()

    def add_item(self, user_id: int, item_id: str, quantity: int = 1):
        self.conn.execute(
            """
            INSERT INTO inventory (user_id, item_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (user_id, item_id, quantity),
        )
        self.conn.commit()

    def inventory(self, user_id: int):
        rows = self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id=? ORDER BY item_id", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def ranking(self, guild_id: int, mode: str):
        column = "level" if mode == "level" else "coins" if mode == "coins" else "rep"
        rows = self.conn.execute(
            f"SELECT * FROM users WHERE guild_id=? ORDER BY {column} DESC, xp DESC LIMIT 10",
            (guild_id,),
        ).fetchall()
        return [dict(row) for row in rows]


db = Database(DATABASE_PATH)


def guild_id_of(interaction: discord.Interaction) -> int:
    return interaction.guild.id if interaction.guild else 0


def get_profile(interaction: discord.Interaction, member: discord.User | discord.Member | None = None) -> dict:
    target = member or interaction.user
    user = db.get_user(target.id, guild_id_of(interaction), str(target))
    user["name"] = str(target)
    if interaction.guild:
        user["guild_id"] = interaction.guild.id
    db.save_user(user)
    return user


def add_xp(user: dict, amount: int) -> bool:
    user["xp"] += amount
    leveled = False
    while user["xp"] >= xp_needed(user["level"]):
        user["xp"] -= xp_needed(user["level"])
        user["level"] += 1
        user["coins"] += 75
        leveled = True
    return leveled


def badge_line(user: dict) -> str:
    badges = [b for b in user.get("badges", "").split(",") if b]
    if not badges:
        return f"{e('BADGE')} nenhuma badge ainda"
    visual = []
    for badge in badges[:6]:
        if badge.lower() == "vip":
            visual.append(f"{e('VIP')} VIP")
        elif badge.lower() == "premium":
            visual.append(f"{e('PREMIUM')} Premium")
        elif badge.lower() == "coroa":
            visual.append(f"{e('COROA')} Coroa")
        elif badge.lower() == "diamante":
            visual.append(f"{e('DIAMANTE')} Diamante")
        else:
            visual.append(f"{e('BADGE')} {badge}")
    return "  ".join(visual)


def profile_embed(target: discord.User | discord.Member, user: dict) -> discord.Embed:
    needed = xp_needed(user["level"])
    embed = discord.Embed(
        title=f"{e('PERFIL')} Perfil de {target.display_name}",
        description=(
            f"-# perfil social personalizado da comunidade\n\n"
            f"{e('BIO')} **Bio**\n"
            f"> {user['bio']}\n\n"
            f"{e('LEVEL')} **Level:** `{user['level']}`\n"
            f"{e('XP')} **XP:** `{progress_bar(user['xp'], needed)}` `{user['xp']}/{needed}`\n"
            f"{e('MOEDA')} **{CURRENCY_NAME}:** `{user['coins']}`\n"
            f"{e('ESTRELA')} **Reputação:** `{user['rep']}`\n\n"
            f"{e('BADGE')} **Badges**\n"
            f"> {badge_line(user)}"
        ),
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.set_footer(text=f"{BRAND_NAME} • bot demo personalizável")
    return embed


class ProfileView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label="Daily", style=discord.ButtonStyle.success)
    async def daily_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Esse botão é do perfil de outra pessoa.", ephemeral=True)
            return
        await daily.callback(interaction)

    @discord.ui.button(label="Loja", style=discord.ButtonStyle.primary)
    async def shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await loja.callback(interaction)

    @discord.ui.button(label="Ranking", style=discord.ButtonStyle.secondary)
    async def rank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await rank.callback(interaction, RANK_CHOICES[0])


class AstraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()


bot = AstraBot()


@bot.event
async def on_ready():
    print(f"{bot.user} online | {BRAND_NAME}")


@bot.tree.command(name="demo", description="Mostra uma vitrine rápida do Astra Social.")
async def demo(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{e('DIAMANTE')} {BRAND_NAME} — Demo",
        description=(
            f"{e('INFO')} Um bot personalizado com a cara da comunidade.\n\n"
            f"{e('PERFIL')} Perfil social\n"
            f"{e('MOEDA')} Economia própria\n"
            f"{e('RANKING')} Ranking\n"
            f"{e('LOJA')} Loja e inventário\n"
            f"{e('BADGE')} Badges exclusivas\n"
            f"{e('ANUNCIO')} Embeds bonitos\n\n"
            f"-# Use `/perfil`, `/daily`, `/loja`, `/rank` e `/embed-demo` para testar."
        ),
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="template vendável para servidores Discord")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="perfil", description="Mostra seu perfil ou o perfil de outro membro.")
@app_commands.describe(membro="Membro que você quer ver")
async def perfil(interaction: discord.Interaction, membro: discord.Member | None = None):
    target = membro or interaction.user
    user = get_profile(interaction, target)
    await interaction.response.send_message(embed=profile_embed(target, user), view=ProfileView(target.id))


@bot.tree.command(name="setbio", description="Configura a bio do seu perfil.")
@app_commands.describe(texto="Sua nova bio")
async def setbio(interaction: discord.Interaction, texto: str):
    user = get_profile(interaction)
    user["bio"] = clean_text(texto, 140)
    add_xp(user, 10)
    db.save_user(user)
    await interaction.response.send_message(
        f"{e('SUCESSO')} Bio atualizada com sucesso.",
        embed=profile_embed(interaction.user, user),
        ephemeral=True,
    )


@bot.tree.command(name="daily", description="Resgata sua recompensa diária.")
async def daily(interaction: discord.Interaction):
    user = get_profile(interaction)
    if user.get("last_daily") == today_key():
        await interaction.response.send_message(f"{e('TEMPO')} Você já pegou o daily hoje. Volte amanhã.", ephemeral=True)
        return
    reward = random.randint(120, 230)
    user["coins"] += reward
    user["last_daily"] = today_key()
    leveled = add_xp(user, 25)
    db.save_user(user)
    msg = f"{e('PRESENTE')} Você recebeu **{reward} {CURRENCY_NAME}**."
    if leveled:
        msg += f"\n{e('LEVEL')} Você subiu de level!"
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, user))


@bot.tree.command(name="trabalhar", description="Trabalhe para ganhar moedas e XP.")
async def trabalhar(interaction: discord.Interaction):
    user = get_profile(interaction)
    current = now_ts()
    cooldown = 20 * 60
    remaining = cooldown - (current - int(user.get("last_work", 0)))
    if remaining > 0:
        await interaction.response.send_message(f"{e('TEMPO')} Espere mais **{max(1, remaining // 60)} min** para trabalhar de novo.", ephemeral=True)
        return
    jobs = [
        "criou um embed bonito para o servidor",
        "ajudou a organizar a comunidade",
        "entregou uma encomenda da loja",
        "participou de um evento rápido",
        "achou moedas escondidas no servidor",
    ]
    reward = random.randint(60, 140)
    user["coins"] += reward
    user["last_work"] = current
    leveled = add_xp(user, 35)
    db.save_user(user)
    msg = f"{e('TRABALHAR')} Você {random.choice(jobs)} e ganhou **{reward} {CURRENCY_NAME}**."
    if leveled:
        msg += f"\n{e('LEVEL')} Level up!"
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, user))


@bot.tree.command(name="rep", description="Dá reputação para alguém.")
@app_commands.describe(membro="Membro que vai receber reputação")
async def rep(interaction: discord.Interaction, membro: discord.Member):
    if membro.id == interaction.user.id:
        await interaction.response.send_message(f"{e('ERRO')} Você não pode dar reputação para si mesmo.", ephemeral=True)
        return
    giver = get_profile(interaction)
    current = now_ts()
    cooldown = 12 * 60 * 60
    remaining = cooldown - (current - int(giver.get("last_rep", 0)))
    if remaining > 0:
        hours = max(1, remaining // 3600)
        await interaction.response.send_message(f"{e('TEMPO')} Você só pode dar rep novamente em **{hours}h**.", ephemeral=True)
        return
    receiver = get_profile(interaction, membro)
    receiver["rep"] += 1
    giver["last_rep"] = current
    add_xp(giver, 10)
    add_xp(receiver, 15)
    db.save_user(giver)
    db.save_user(receiver)
    await interaction.response.send_message(f"{e('ESTRELA')} {interaction.user.mention} deu reputação para {membro.mention}.")


@bot.tree.command(name="loja", description="Mostra a loja da comunidade.")
async def loja(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{e('LOJA')} Loja da Comunidade",
        description=f"Use `/comprar` para comprar itens com {e('MOEDA')} **{CURRENCY_NAME}**.",
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    for item_id, item in SHOP_ITEMS.items():
        embed.add_field(
            name=f"{item['emoji']} {item['name']} — {item['price']} coins",
            value=f"ID: `{item_id}`\n{item['desc']}",
            inline=False,
        )
    embed.set_footer(text=f"{BRAND_NAME} • loja configurável")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="comprar", description="Compra um item da loja.")
@app_commands.describe(item="Item que deseja comprar")
@app_commands.choices(item=ITEM_CHOICES)
async def comprar(interaction: discord.Interaction, item: app_commands.Choice[str]):
    user = get_profile(interaction)
    data = SHOP_ITEMS[item.value]
    if user["coins"] < data["price"]:
        await interaction.response.send_message(f"{e('ERRO')} Você não tem moedas suficientes.", ephemeral=True)
        return
    user["coins"] -= data["price"]
    if data["type"] == "badge":
        badges = [b for b in user.get("badges", "").split(",") if b]
        if data["badge"] not in badges:
            badges.append(data["badge"])
        user["badges"] = ",".join(badges)
        msg = f"{e('SUCESSO')} Você comprou a badge **{data['name']}**."
    else:
        reward = random.randint(80, 280)
        user["coins"] += reward
        msg = f"{e('CAIXA')} Você abriu uma caixa e ganhou **{reward} {CURRENCY_NAME}**."
    add_xp(user, 20)
    db.add_item(interaction.user.id, item.value, 1)
    db.save_user(user)
    await interaction.response.send_message(msg, embed=profile_embed(interaction.user, user))


@bot.tree.command(name="inventario", description="Mostra seu inventário.")
async def inventario(interaction: discord.Interaction):
    get_profile(interaction)
    inv = db.inventory(interaction.user.id)
    embed = discord.Embed(title=f"{e('INVENTARIO')} Inventário", color=COLOR_MAIN, timestamp=datetime.now(timezone.utc))
    if not inv:
        embed.description = f"{e('CAIXA')} Seu inventário está vazio. Use `/loja`."
    else:
        lines = []
        for row in inv:
            item = SHOP_ITEMS.get(row["item_id"])
            if item:
                lines.append(f"{item['emoji']} **{item['name']}** x{row['quantity']}")
        embed.description = "\n".join(lines)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rank", description="Ranking do servidor por level, moedas ou reputação.")
@app_commands.describe(tipo="Tipo de ranking")
@app_commands.choices(tipo=RANK_CHOICES)
async def rank(interaction: discord.Interaction, tipo: app_commands.Choice[str] = RANK_CHOICES[0]):
    if not interaction.guild:
        await interaction.response.send_message(f"{e('AVISO')} Ranking funciona melhor dentro de um servidor.", ephemeral=True)
        return
    get_profile(interaction)
    rows = db.ranking(interaction.guild.id, tipo.value)
    embed = discord.Embed(
        title=f"{e('RANKING')} Ranking — {tipo.name}",
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    if not rows:
        embed.description = "Ninguém entrou no ranking ainda."
    else:
        lines = []
        medals = [e("COROA"), e("DIAMANTE"), e("ESTRELA")]
        for index, user in enumerate(rows, start=1):
            medal = medals[index - 1] if index <= 3 else f"`#{index}`"
            value = user["level"] if tipo.value == "level" else user["coins"] if tipo.value == "coins" else user["rep"]
            lines.append(f"{medal} <@{user['user_id']}> — **{value}**")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"{BRAND_NAME} • ranking personalizável")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="embed-demo", description="Cria um anúncio bonito de demonstração.")
@app_commands.describe(titulo="Título do anúncio", texto="Texto do anúncio")
async def embed_demo(interaction: discord.Interaction, titulo: str = "Evento da Comunidade", texto: str = "Hoje teremos evento valendo recompensas especiais."):
    embed = discord.Embed(
        title=f"{e('ANUNCIO')} {clean_text(titulo, 80)}",
        description=(
            f"{e('SETA')} {clean_text(texto, 600)}\n\n"
            f"{e('PRESENTE')} **Recompensas:** moedas, badges e destaque no ranking\n"
            f"{e('TEMPO')} **Status:** aberto para participação"
        ),
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{BRAND_NAME} • anúncio personalizado")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda", description="Mostra os comandos da demo.")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{e('INFO')} Comandos da Demo",
        description="Teste os principais sistemas do bot personalizável.",
        color=COLOR_MAIN,
    )
    embed.add_field(name=f"{e('PERFIL')} Perfil", value="`/perfil` `/setbio` `/rep`", inline=False)
    embed.add_field(name=f"{e('MOEDA')} Economia", value="`/daily` `/trabalhar` `/rank`", inline=False)
    embed.add_field(name=f"{e('LOJA')} Loja", value="`/loja` `/comprar` `/inventario`", inline=False)
    embed.add_field(name=f"{e('ANUNCIO')} Demonstração", value="`/demo` `/embed-demo`", inline=False)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Defina DISCORD_TOKEN no Railway.")
    bot.run(DISCORD_TOKEN)
