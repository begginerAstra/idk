from astra_social import TOKEN, bot

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Defina DISCORD_TOKEN no Railway.")
    bot.run(TOKEN)
