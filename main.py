import os
import sqlite3
import random
from datetime import datetime, timezone, date

import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BRAND_NAME = os.getenv("BRAND_NAME", "Cantinho dos Gatinhos")
DATABASE_PATH = os.getenv("DATABASE_PATH", "cats.db")

COLOR_MAIN = 0xF7A8C7
COLOR_OK = 0x7ED957
COLOR_WARN = 0xFFD966
COLOR_ERROR = 0xFF6B6B

CAT_TYPES = {
    "laranja": {"emoji": "🐈", "label": "Gatinho Laranja"},
    "preto": {"emoji": "🐈‍⬛", "label": "Gatinho Preto"},
    "branco": {"emoji": "🤍", "label": "Gatinho Branco"},
    "cinza": {"emoji": "🩶", "label": "Gatinho Cinza"},
    "siames": {"emoji": "😺", "label": "Gatinho Siamês"},
}

SHOP = {
    "racao": {"name": "Ração Premium", "emoji": "🍗", "price": 35, "kind": "food", "power": 28, "desc": "+28 fome"},
    "atum": {"name": "Atum Chique", "emoji": "🐟", "price": 55, "kind": "food", "power": 45, "desc": "+45 fome"},
    "bolinha": {"name": "Bolinha Colorida", "emoji": "🧶", "price": 45, "kind": "toy", "power": 25, "desc": "+25 felicidade"},
    "varinha": {"name": "Varinha de Penas", "emoji": "🪶", "price": 70, "kind": "toy", "power": 42, "desc": "+42 felicidade"},
    "caminha": {"name": "Caminha Fofinha", "emoji": "🛏️", "price": 85, "kind": "bed", "power": 45, "desc": "+45 energia"},
    "laco": {"name": "Laço Rosa", "emoji": "🎀", "price": 120, "kind": "cosmetic", "power": 0, "desc": "cosmético"},
    "coroa": {"name": "Coroa Real", "emoji": "👑", "price": 250, "kind": "cosmetic", "power": 0, "desc": "cosmético raro"},
}

MOODS = [
    "ronronando baixinho",
    "fazendo pãozinho",
    "te olhando com carinha pidona",
    "dormindo enroladinho",
    "caçando uma meia perdida",
    "pedindo carinho",
]


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def today_key() -> str:
    return date.today().isoformat()


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))


def bar(value: int) -> str:
    filled = max(0, min(10, round(value / 10)))
    return "█" * filled + "░" * (10 - filled)


def rarity_title(level: int) -> str:
    if level >= 30:
        return "Lenda Felina"
    if level >= 20:
        return "Mestre dos Ronrons"
    if level >= 10:
        return "Tutor Experiente"
    if level >= 5:
        return "Cuidador Carinhoso"
    return "Novo Tutor"


def xp_needed(level: int) -> int:
    return 100 + (level - 1) * 35


class CatDatabase:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cats (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_name TEXT NOT NULL,
                name TEXT NOT NULL,
                cat_type TEXT NOT NULL,
                hunger INTEGER NOT NULL DEFAULT 80,
                happiness INTEGER NOT NULL DEFAULT 80,
                energy INTEGER NOT NULL DEFAULT 80,
                hygiene INTEGER NOT NULL DEFAULT 80,
                coins INTEGER NOT NULL DEFAULT 120,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                adopted_at INTEGER NOT NULL,
                last_decay INTEGER NOT NULL,
                last_daily TEXT,
                last_work INTEGER NOT NULL DEFAULT 0
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

    def get_cat(self, user_id: int):
        row = self.conn.execute("SELECT * FROM cats WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        cat = dict(row)
        cat = self.apply_decay(cat)
        return cat

    def create_cat(self, user_id: int, guild_id: int, owner_name: str, name: str, cat_type: str):
        ts = now_ts()
        self.conn.execute(
            """
            INSERT INTO cats (user_id, guild_id, owner_name, name, cat_type, hunger, happiness, energy, hygiene, coins, level, xp, adopted_at, last_decay)
            VALUES (?, ?, ?, ?, ?, 85, 85, 85, 85, 150, 1, 0, ?, ?)
            """,
            (user_id, guild_id, owner_name, name, cat_type, ts, ts),
        )
        self.conn.commit()
        return self.get_cat(user_id)

    def save_cat(self, cat: dict):
        self.conn.execute(
            """
            UPDATE cats SET owner_name=?, name=?, cat_type=?, hunger=?, happiness=?, energy=?, hygiene=?, coins=?, level=?, xp=?, last_decay=?, last_daily=?, last_work=?
            WHERE user_id=?
            """,
            (
                cat["owner_name"], cat["name"], cat["cat_type"], cat["hunger"], cat["happiness"], cat["energy"], cat["hygiene"],
                cat["coins"], cat["level"], cat["xp"], cat["last_decay"], cat.get("last_daily"), cat.get("last_work", 0), cat["user_id"]
            ),
        )
        self.conn.commit()

    def apply_decay(self, cat: dict):
        current = now_ts()
        elapsed_hours = max(0, (current - int(cat["last_decay"])) // 3600)
        if elapsed_hours <= 0:
            return cat
        cat["hunger"] = clamp(cat["hunger"] - elapsed_hours * 3)
        cat["happiness"] = clamp(cat["happiness"] - elapsed_hours * 2)
        cat["energy"] = clamp(cat["energy"] - elapsed_hours * 2)
        cat["hygiene"] = clamp(cat["hygiene"] - elapsed_hours * 2)
        cat["last_decay"] = current
        self.save_cat(cat)
        return cat

    def add_item(self, user_id: int, item_id: str, quantity: int):
        self.conn.execute(
            """
            INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (user_id, item_id, quantity),
        )
        self.conn.commit()

    def use_item(self, user_id: int, item_id: str) -> bool:
        row = self.conn.execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)).fetchone()
        if not row or row["quantity"] <= 0:
            return False
        new_quantity = row["quantity"] - 1
        if new_quantity <= 0:
            self.conn.execute("DELETE FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id))
        else:
            self.conn.execute("UPDATE inventory SET quantity=? WHERE user_id=? AND item_id=?", (new_quantity, user_id, item_id))
        self.conn.commit()
        return True

    def inventory(self, user_id: int):
        rows = self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id=? ORDER BY item_id", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def leaderboard(self, guild_id: int, limit: int = 10):
        rows = self.conn.execute(
            "SELECT * FROM cats WHERE guild_id=? ORDER BY level DESC, xp DESC, coins DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


db = CatDatabase(DATABASE_PATH)


def cat_emoji(cat: dict) -> str:
    return CAT_TYPES.get(cat["cat_type"], CAT_TYPES["laranja"])["emoji"]


def add_xp(cat: dict, amount: int):
    cat["xp"] += amount
    leveled = False
    while cat["xp"] >= xp_needed(cat["level"]):
        cat["xp"] -= xp_needed(cat["level"])
        cat["level"] += 1
        cat["coins"] += 50
        leveled = True
    return leveled


def cat_embed(cat: dict, title: str | None = None) -> discord.Embed:
    emoji = cat_emoji(cat)
    health = round((cat["hunger"] + cat["happiness"] + cat["energy"] + cat["hygiene"]) / 4)
    mood = random.choice(MOODS)
    embed = discord.Embed(
        title=title or f"{emoji} {cat['name']}",
        description=f"**{cat['name']}** está {mood}.\n**Título:** {rarity_title(cat['level'])}",
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🍗 Fome", value=f"`{bar(cat['hunger'])}` {cat['hunger']}%", inline=False)
    embed.add_field(name="💖 Felicidade", value=f"`{bar(cat['happiness'])}` {cat['happiness']}%", inline=False)
    embed.add_field(name="⚡ Energia", value=f"`{bar(cat['energy'])}` {cat['energy']}%", inline=False)
    embed.add_field(name="🧼 Higiene", value=f"`{bar(cat['hygiene'])}` {cat['hygiene']}%", inline=False)
    embed.add_field(name="✨ Level", value=f"**{cat['level']}** | XP `{cat['xp']}/{xp_needed(cat['level'])}`", inline=True)
    embed.add_field(name="🪙 Moedas", value=f"**{cat['coins']}**", inline=True)
    embed.add_field(name="🌡️ Bem-estar", value=f"**{health}%**", inline=True)
    embed.set_footer(text=BRAND_NAME)
    return embed


async def require_cat(interaction: discord.Interaction):
    cat = db.get_cat(interaction.user.id)
    if not cat:
        await interaction.response.send_message("🐾 Você ainda não adotou um gatinho. Use `/adotar` primeiro.", ephemeral=True)
        return None
    return cat


class CatCareView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def check_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("🐾 Esse gatinho não é seu. Use `/adotar` para ter o seu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Alimentar", emoji="🍗", style=discord.ButtonStyle.success)
    async def feed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
        cat = db.get_cat(interaction.user.id)
        if not cat:
            await interaction.response.send_message("Use `/adotar` primeiro.", ephemeral=True)
            return
        cat["hunger"] = clamp(cat["hunger"] + 18)
        cat["happiness"] = clamp(cat["happiness"] + 4)
        leveled = add_xp(cat, 12)
        db.save_cat(cat)
        msg = "🍗 Você alimentou seu gatinho."
        if leveled:
            msg += " ✨ Ele subiu de level!"
        await interaction.response.edit_message(content=msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))

    @discord.ui.button(label="Brincar", emoji="🧶", style=discord.ButtonStyle.primary)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
        cat = db.get_cat(interaction.user.id)
        if not cat:
            await interaction.response.send_message("Use `/adotar` primeiro.", ephemeral=True)
            return
        if cat["energy"] < 12:
            await interaction.response.send_message("😴 Seu gatinho está cansado. Deixe ele dormir um pouco.", ephemeral=True)
            return
        cat["happiness"] = clamp(cat["happiness"] + 20)
        cat["energy"] = clamp(cat["energy"] - 10)
        cat["hunger"] = clamp(cat["hunger"] - 5)
        leveled = add_xp(cat, 16)
        cat["coins"] += random.randint(4, 12)
        db.save_cat(cat)
        msg = "🧶 Vocês brincaram juntos."
        if leveled:
            msg += " ✨ Level up!"
        await interaction.response.edit_message(content=msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))

    @discord.ui.button(label="Carinho", emoji="💖", style=discord.ButtonStyle.secondary)
    async def pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
        cat = db.get_cat(interaction.user.id)
        if not cat:
            await interaction.response.send_message("Use `/adotar` primeiro.", ephemeral=True)
            return
        cat["happiness"] = clamp(cat["happiness"] + 12)
        leveled = add_xp(cat, 8)
        db.save_cat(cat)
        msg = "💖 Seu gatinho ronronou com o carinho."
        if leveled:
            msg += " ✨ Subiu de level!"
        await interaction.response.edit_message(content=msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))

    @discord.ui.button(label="Banho", emoji="🧼", style=discord.ButtonStyle.secondary)
    async def clean(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
        cat = db.get_cat(interaction.user.id)
        if not cat:
            await interaction.response.send_message("Use `/adotar` primeiro.", ephemeral=True)
            return
        cat["hygiene"] = clamp(cat["hygiene"] + 25)
        cat["happiness"] = clamp(cat["happiness"] - 3)
        leveled = add_xp(cat, 10)
        db.save_cat(cat)
        msg = "🧼 Banho tomado. Ele fingiu que odiou, mas ficou cheiroso."
        if leveled:
            msg += " ✨ Level up!"
        await interaction.response.edit_message(content=msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))

    @discord.ui.button(label="Dormir", emoji="😴", style=discord.ButtonStyle.secondary)
    async def sleep(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_owner(interaction):
            return
        cat = db.get_cat(interaction.user.id)
        if not cat:
            await interaction.response.send_message("Use `/adotar` primeiro.", ephemeral=True)
            return
        cat["energy"] = clamp(cat["energy"] + 30)
        cat["hunger"] = clamp(cat["hunger"] - 4)
        leveled = add_xp(cat, 10)
        db.save_cat(cat)
        msg = "😴 Seu gatinho tirou uma soneca gostosa."
        if leveled:
            msg += " ✨ Subiu de level!"
        await interaction.response.edit_message(content=msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))


class CatBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()


bot = CatBot()


@bot.event
async def on_ready():
    print(f"✅ {bot.user} online | {BRAND_NAME} carregado")


@bot.tree.command(name="adotar", description="Adote seu primeiro gatinho virtual.")
@app_commands.describe(nome="Nome do seu gatinho", tipo="Tipo/cor do gatinho")
@app_commands.choices(tipo=[
    app_commands.Choice(name="🐈 Gatinho Laranja", value="laranja"),
    app_commands.Choice(name="🐈‍⬛ Gatinho Preto", value="preto"),
    app_commands.Choice(name="🤍 Gatinho Branco", value="branco"),
    app_commands.Choice(name="🩶 Gatinho Cinza", value="cinza"),
    app_commands.Choice(name="😺 Gatinho Siamês", value="siames"),
])
async def adotar(interaction: discord.Interaction, nome: str, tipo: app_commands.Choice[str]):
    if not interaction.guild:
        await interaction.response.send_message("Esse comando só funciona em servidor.", ephemeral=True)
        return
    if db.get_cat(interaction.user.id):
        await interaction.response.send_message("🐾 Você já tem um gatinho. Use `/meu-gato` para ver ele.", ephemeral=True)
        return
    clean_name = nome.strip()[:24]
    if len(clean_name) < 2:
        await interaction.response.send_message("Escolha um nome com pelo menos 2 letras.", ephemeral=True)
        return
    cat = db.create_cat(interaction.user.id, interaction.guild.id, str(interaction.user), clean_name, tipo.value)
    embed = cat_embed(cat, title=f"🎉 Adoção concluída: {cat_emoji(cat)} {clean_name}")
    embed.description = f"{interaction.user.mention} adotou **{clean_name}**! Cuide bem dele todos os dias."
    await interaction.response.send_message(embed=embed, view=CatCareView(interaction.user.id))


@bot.tree.command(name="meu-gato", description="Veja o status do seu gatinho.")
async def meu_gato(interaction: discord.Interaction):
    cat = await require_cat(interaction)
    if not cat:
        return
    await interaction.response.send_message(embed=cat_embed(cat), view=CatCareView(interaction.user.id))


@bot.tree.command(name="nomear", description="Troque o nome do seu gatinho.")
@app_commands.describe(novo_nome="Novo nome do gatinho")
async def nomear(interaction: discord.Interaction, novo_nome: str):
    cat = await require_cat(interaction)
    if not cat:
        return
    clean = novo_nome.strip()[:24]
    if len(clean) < 2:
        await interaction.response.send_message("Escolha um nome com pelo menos 2 letras.", ephemeral=True)
        return
    old = cat["name"]
    cat["name"] = clean
    db.save_cat(cat)
    await interaction.response.send_message(f"✅ Nome alterado de **{old}** para **{clean}**.", embed=cat_embed(cat))


@bot.tree.command(name="daily", description="Pegue moedas diárias para cuidar do seu gatinho.")
async def daily(interaction: discord.Interaction):
    cat = await require_cat(interaction)
    if not cat:
        return
    if cat.get("last_daily") == today_key():
        await interaction.response.send_message("⏰ Você já pegou seu prêmio diário hoje. Volte amanhã.", ephemeral=True)
        return
    reward = random.randint(90, 160)
    cat["coins"] += reward
    cat["last_daily"] = today_key()
    leveled = add_xp(cat, 15)
    db.save_cat(cat)
    text = f"🎁 Você recebeu **{reward} moedas** para cuidar do seu gatinho."
    if leveled:
        text += " ✨ Seu gatinho subiu de level!"
    await interaction.response.send_message(text, embed=cat_embed(cat))


@bot.tree.command(name="trabalhar", description="Faça uma tarefa rápida para ganhar moedas.")
async def trabalhar(interaction: discord.Interaction):
    cat = await require_cat(interaction)
    if not cat:
        return
    current = now_ts()
    cooldown = 20 * 60
    remaining = cooldown - (current - int(cat.get("last_work", 0)))
    if remaining > 0:
        minutes = max(1, remaining // 60)
        await interaction.response.send_message(f"⏰ Espere mais **{minutes} min** para trabalhar de novo.", ephemeral=True)
        return
    jobs = [
        "você ajudou numa lojinha de pets",
        "você tirou fotos fofas do seu gatinho",
        "seu gatinho achou moedinhas debaixo do sofá",
        "vocês entregaram sachês para outros gatos",
        "seu gatinho viralizou por 5 minutos",
    ]
    reward = random.randint(35, 90)
    cat["coins"] += reward
    cat["last_work"] = current
    cat["energy"] = clamp(cat["energy"] - 8)
    leveled = add_xp(cat, 18)
    db.save_cat(cat)
    text = f"💼 {random.choice(jobs)} e ganhou **{reward} moedas**."
    if leveled:
        text += " ✨ Level up!"
    await interaction.response.send_message(text, embed=cat_embed(cat))


@bot.tree.command(name="loja", description="Veja a loja de itens para gatinhos.")
async def loja(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 Loja dos Gatinhos",
        description="Use `/comprar item quantidade` para comprar e `/usar item` para usar.",
        color=COLOR_MAIN,
        timestamp=datetime.now(timezone.utc),
    )
    for item_id, item in SHOP.items():
        embed.add_field(
            name=f"{item['emoji']} {item['name']} — {item['price']} moedas",
            value=f"ID: `{item_id}` | {item['desc']}",
            inline=False,
        )
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


ITEM_CHOICES = [app_commands.Choice(name=f"{data['emoji']} {data['name']}", value=item_id) for item_id, data in SHOP.items()]


@bot.tree.command(name="comprar", description="Compre itens para seu gatinho.")
@app_commands.describe(item="Item da loja", quantidade="Quantidade")
@app_commands.choices(item=ITEM_CHOICES)
async def comprar(interaction: discord.Interaction, item: app_commands.Choice[str], quantidade: int = 1):
    cat = await require_cat(interaction)
    if not cat:
        return
    if quantidade < 1 or quantidade > 20:
        await interaction.response.send_message("A quantidade precisa ser entre 1 e 20.", ephemeral=True)
        return
    data = SHOP[item.value]
    total = data["price"] * quantidade
    if cat["coins"] < total:
        await interaction.response.send_message(f"🪙 Você precisa de **{total} moedas**, mas só tem **{cat['coins']}**.", ephemeral=True)
        return
    cat["coins"] -= total
    db.save_cat(cat)
    db.add_item(interaction.user.id, item.value, quantidade)
    await interaction.response.send_message(f"✅ Comprou **{quantidade}x {data['emoji']} {data['name']}** por **{total} moedas**.", embed=cat_embed(cat))


@bot.tree.command(name="inventario", description="Veja seus itens comprados.")
async def inventario(interaction: discord.Interaction):
    cat = await require_cat(interaction)
    if not cat:
        return
    inv = db.inventory(interaction.user.id)
    embed = discord.Embed(title="🎒 Inventário", color=COLOR_MAIN, timestamp=datetime.now(timezone.utc))
    if not inv:
        embed.description = "Seu inventário está vazio. Use `/loja` para comprar itens."
    else:
        lines = []
        for row in inv:
            item = SHOP.get(row["item_id"])
            if item:
                lines.append(f"{item['emoji']} **{item['name']}** x{row['quantity']} — ID `{row['item_id']}`")
        embed.description = "\n".join(lines) if lines else "Nenhum item válido encontrado."
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="usar", description="Use um item do inventário no seu gatinho.")
@app_commands.describe(item="Item que você quer usar")
@app_commands.choices(item=ITEM_CHOICES)
async def usar(interaction: discord.Interaction, item: app_commands.Choice[str]):
    cat = await require_cat(interaction)
    if not cat:
        return
    data = SHOP[item.value]
    if not db.use_item(interaction.user.id, item.value):
        await interaction.response.send_message("❌ Você não tem esse item no inventário.", ephemeral=True)
        return
    kind = data["kind"]
    if kind == "food":
        cat["hunger"] = clamp(cat["hunger"] + data["power"])
        cat["happiness"] = clamp(cat["happiness"] + 3)
    elif kind == "toy":
        cat["happiness"] = clamp(cat["happiness"] + data["power"])
        cat["energy"] = clamp(cat["energy"] - 5)
    elif kind == "bed":
        cat["energy"] = clamp(cat["energy"] + data["power"])
    elif kind == "cosmetic":
        cat["happiness"] = clamp(cat["happiness"] + 10)
    leveled = add_xp(cat, 15)
    db.save_cat(cat)
    msg = f"✅ Você usou **{data['emoji']} {data['name']}** em **{cat['name']}**."
    if leveled:
        msg += " ✨ Ele subiu de level!"
    await interaction.response.send_message(msg, embed=cat_embed(cat), view=CatCareView(interaction.user.id))


@bot.tree.command(name="ranking", description="Veja os gatinhos mais evoluídos do servidor.")
async def ranking(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Esse comando só funciona em servidor.", ephemeral=True)
        return
    rows = db.leaderboard(interaction.guild.id, 10)
    embed = discord.Embed(title="🏆 Ranking dos Gatinhos", color=COLOR_MAIN, timestamp=datetime.now(timezone.utc))
    if not rows:
        embed.description = "Ainda não tem gatinhos neste servidor. Use `/adotar`."
    else:
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for index, cat in enumerate(rows, start=1):
            medal = medals[index - 1] if index <= 3 else f"`#{index}`"
            lines.append(f"{medal} {cat_emoji(cat)} **{cat['name']}** — Level **{cat['level']}** | Tutor: <@{cat['user_id']}>")
        embed.description = "\n".join(lines)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ajuda-gato", description="Mostra todos os comandos do bot de gatinhos.")
async def ajuda_gato(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"🐾 {BRAND_NAME}",
        description="Um bot fofo de cuidar de gatinhos virtuais.",
        color=COLOR_MAIN,
    )
    embed.add_field(name="Começo", value="`/adotar` — adota um gatinho\n`/meu-gato` — vê o status\n`/nomear` — troca o nome", inline=False)
    embed.add_field(name="Cuidados", value="Use os botões em `/meu-gato` para alimentar, brincar, dar carinho, banho e dormir.", inline=False)
    embed.add_field(name="Economia", value="`/daily` — prêmio diário\n`/trabalhar` — ganha moedas\n`/loja` `/comprar` `/inventario` `/usar`", inline=False)
    embed.add_field(name="Social", value="`/ranking` — ranking dos gatinhos do servidor", inline=False)
    embed.set_footer(text=BRAND_NAME)
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Defina a variável DISCORD_TOKEN no Railway.")
    bot.run(DISCORD_TOKEN)
