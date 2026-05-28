# Cantinho dos Gatinhos

Bot Discord fofo para cuidar de gatinhos virtuais, feito em Python com `discord.py`.

## Recursos

- Adotar um gatinho virtual.
- Escolher tipo/cor do gatinho.
- Status com fome, felicidade, energia e higiene.
- Botões para alimentar, brincar, dar carinho, dar banho e dormir.
- Sistema de level e XP.
- Moedas virtuais.
- Prêmio diário.
- Trabalho com cooldown para ganhar moedas.
- Loja de itens.
- Inventário.
- Uso de itens para melhorar os atributos do gatinho.
- Ranking dos gatinhos do servidor.
- Banco local SQLite, sem Supabase/Firebase obrigatório.

## Comandos

```txt
/adotar
/meu-gato
/nomear
/daily
/trabalhar
/loja
/comprar
/inventario
/usar
/ranking
/ajuda-gato
```

## Configuração no Discord Developer Portal

1. Crie uma aplicação em https://discord.com/developers/applications
2. Vá em **Bot** e crie o bot.
3. Copie o token.
4. Em **OAuth2 > URL Generator**, marque:
   - `bot`
   - `applications.commands`
5. Permissões recomendadas:
   - Send Messages
   - Embed Links
   - Use Slash Commands
   - Read Message History

## Link de convite

Troque `CLIENT_ID_AQUI` pelo Client ID do seu bot:

```txt
https://discord.com/oauth2/authorize?client_id=CLIENT_ID_AQUI&permissions=84992&integration_type=0&scope=bot+applications.commands
```

## Configuração no Railway

No Railway, adicione estas variáveis:

```env
DISCORD_TOKEN=seu_token_do_discord
BRAND_NAME=Cantinho dos Gatinhos
DATABASE_PATH=cats.db
```

A única obrigatória é:

```env
DISCORD_TOKEN=seu_token_do_discord
```

## Deploy

O Railway vai usar o `Procfile`:

```txt
worker: python main.py
```

## Rodar localmente

```bash
pip install -r requirements.txt
DISCORD_TOKEN=seu_token python main.py
```

No Windows PowerShell:

```powershell
$env:DISCORD_TOKEN="seu_token"
python main.py
```

## Observação importante

O banco SQLite `cats.db` funciona bem para começar. Em hospedagens gratuitas, o arquivo pode ser perdido se o serviço recriar o container. Para uma versão premium/monetizável, o ideal depois é migrar para PostgreSQL/Supabase.
