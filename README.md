# Astra Roblox Stalk Bot

Bot Discord em Python com comando `/stalk` para analisar perfis públicos do Roblox.

## Recursos

- Resolve username Roblox para ID.
- Mostra avatar, headshot e link do perfil.
- Mostra data de criação, idade da conta e status.
- Mostra amigos, seguidores e seguindo.
- Mostra presença pública: offline, online, jogo ou Studio.
- Lista grupos públicos.
- Lista badges recentes.
- Tenta listar collectibles/limiteds públicos.
- Gera score de confiança visual.

## Configuração no Discord Developer Portal

1. Crie uma aplicação em https://discord.com/developers/applications
2. Vá em **Bot** e crie o bot.
3. Copie o token.
4. Ative as permissões necessárias para slash commands.
5. Em **OAuth2 > URL Generator**, marque:
   - `bot`
   - `applications.commands`
6. Permissões recomendadas:
   - Send Messages
   - Embed Links
   - Use Slash Commands

## Configuração no Railway

1. Crie um novo projeto no Railway.
2. Escolha **Deploy from GitHub repo**.
3. Selecione este repositório.
4. Vá em **Variables** e adicione:

```env
DISCORD_TOKEN=seu_token_do_discord
```

5. Faça deploy.

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

## Comando

```txt
/stalk username:nomeRoblox
```

## Observação

O bot usa apenas dados públicos das APIs do Roblox. Algumas informações podem aparecer como indisponíveis quando o usuário tiver inventário fechado ou quando a API limitar a resposta.
