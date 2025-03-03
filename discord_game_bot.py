import discord
from discord.ext import commands
import psycopg2
import asyncio
import os
import random

# Vérification et installation de requests si manquant
try:
    import requests
except ModuleNotFoundError:
    import subprocess
    subprocess.run(["pip", "install", "requests"])
    import requests

# Configuration du bot
TOKEN = os.getenv("TOKEN")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Connexion à PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode="require", client_encoding="UTF8")
cursor = conn.cursor()

# Création de la table "games" si elle n'existe pas encore
cursor.execute('''CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE, 
                    release_date TEXT, 
                    price TEXT, 
                    type TEXT, 
                    duration TEXT, 
                    cloud_available TEXT, 
                    youtube_link TEXT, 
                    steam_link TEXT)''')
conn.commit()

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()  # 🔥 Synchronisation des commandes slash
        print("✅ Commandes slash synchronisées avec Discord !")
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes slash : {e}")

    print(f"🤖 Bot connecté en tant que {bot.user}")

def save_database():
    """ Sauvegarde immédiate des changements dans PostgreSQL. """
    conn.commit()
    print("📂 Base de données sauvegardée avec succès sur Railway.")

class CommandesDropdown(discord.ui.Select):
    def __init__(self, is_admin):
        """ Crée un menu déroulant avec les commandes disponibles. """

        # Commandes publiques (nom + description)
        public_commands = {
            "!listejeux": "Affiche tous les jeux enregistrés (triés A-Z)",
            "!types": "Affiche tous les types de jeux enregistrés",
            "!type NomDuType": "Affiche tous les jeux d'un type donné",
            "!ask NomDuJeu": "Demande l'ajout d'un jeu",
            "!proposejeu": "Propose un jeu aléatoire",
            "!proposejeutype NomDuType": "Propose un jeu aléatoire selon un type spécifique"
        }

        # Commandes admin (nom + description)
        admin_commands = {
            "!ajoutjeu Nom Date Prix Type(s) Durée Cloud LienYouTube LienSteam": "Ajoute un jeu à la base",
            "!supprjeu Nom": "Supprime un jeu de la base",
            "!modifjeu Nom Champ NouvelleValeur": "Modifie un champ d’un jeu existant",
            "!demandes": "Affiche la liste des jeux demandés"
        }

        # Créer les options pour le menu déroulant
        options = [
            discord.SelectOption(label=cmd, description=desc)
            for cmd, desc in public_commands.items()
        ]

        # Ajouter les commandes admin si l'utilisateur est admin
        if is_admin:
            options += [
                discord.SelectOption(label=cmd, description=desc)
                for cmd, desc in admin_commands.items()
            ]
        )

class CommandesView(discord.ui.View):
    def __init__(self, is_admin):
        super().__init__(timeout=120)  # Les boutons restent actifs 2 minutes
        self.add_item(CommandesDropdown(is_admin))
        
# 📌 Demander un jeu
@bot.tree.command(name="ask")
async def ask(interaction: discord.Interaction, game_name: str):
    """ Ajoute une demande de jeu avec confirmation """
    user_id = interaction.user.id
    username = interaction.user.name
    game_name = game_name.strip().capitalize()

    try:
        cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
        existing = cursor.fetchone()

        if existing:
            await interaction.response.send_message(f"❌ **{game_name}** est déjà dans la liste des demandes.", ephemeral=True)
            return

        cursor.execute("INSERT INTO game_requests (user_id, username, game_name) VALUES (%s, %s, %s)", (user_id, username, game_name))
        conn.commit()

        await interaction.response.send_message(f"📩 **{game_name}** a été ajouté à la liste des demandes par {username} !")
    
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de l'ajout de la demande : {str(e)}")

# 📌 Voir la liste des demandes (ADMIN)
@bot.tree.command(name="demandes")
@commands.has_permissions(administrator=True)
async def demandes(interaction: discord.Interaction):
    """ Affiche la liste des jeux demandés avec l'utilisateur qui l'a demandé """
    cursor.execute("SELECT username, game_name FROM game_requests ORDER BY date DESC")
    requests = cursor.fetchall()

    if requests:
        request_list = "\n".join([f"- **{r[1]}** (demandé par {r[0]})" for r in requests])
        await interaction.response.send_message(f"📜 **Liste des jeux demandés :**\n```{request_list}```")
    else:
        await interaction.response.send_message("📭 **Aucune demande en attente.**")

# 📌 Supprimer une demande manuellement (ADMIN)
@bot.tree.command(name="supprdemande")
@commands.has_permissions(administrator=True)

async def supprdemande(interaction: discord.Interaction, game_name: str):
    """ Supprime une demande de jeu de la liste """
    cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
    demande = cursor.fetchone()

    if demande:
        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
        conn.commit()
        await interaction.response.send_message(f"🗑️ La demande pour **{game_name.capitalize()}** a été supprimée.")
    else:
        await interaction.response.send_message(f"❌ Aucun jeu trouvé dans la liste des demandes sous le nom '{game_name}'.")

# 📌 Recherche par type (`/type`)
@bot.tree.command(name="type")

# 📌 Modifier un jeu
@bot.tree.command(name="modifjeu")
@commands.has_permissions(administrator=True)
async def modifjeu(interaction: discord.Interaction, name: str, field: str, new_value: str):
    """ Modifie un champ spécifique d'un jeu """
    try:
        name = name.strip().lower()

        cursor.execute("SELECT * FROM games WHERE LOWER(name) LIKE %s", (f"%{name}%",))
        jeu = cursor.fetchone()

        if not jeu:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé avec le nom '{name.capitalize()}'.")
            return

        valid_fields = ["release_date", "price", "type", "duration", "cloud_available", "youtube_link", "steam_link"]
        if field.lower() not in valid_fields:
            await interaction.response.send_message(f"❌ Le champ `{field}` n'est pas valide. Champs disponibles : {', '.join(valid_fields)}")
            return

        query = f"UPDATE games SET {field} = %s WHERE LOWER(name) LIKE %s"
        cursor.execute(query, (new_value, f"%{name}%"))
        conn.commit()

        await interaction.response.send_message(f"✅ Jeu '{jeu[0].capitalize()}' mis à jour : **{field}** → {new_value}")

    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la modification du jeu : {str(e)}")

# 📌 Ajouter un jeu
@bot.tree.command(name="ajoutjeu")
@commands.has_permissions(administrator=True)
async def ajoutjeu(interaction: discord.Interaction, name: str, release_date: str, price: str, types: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    """ Ajoute un jeu à la liste et le supprime des demandes s'il existait dans /ask """
    try:
        cursor.execute(
            "INSERT INTO games (name, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
            (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link)
        )
        save_database()

        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (name.lower(),))
        conn.commit()

        await interaction.response.send_message(f"✅ **{name}** ajouté avec succès et retiré des demandes !")

    except psycopg2.IntegrityError:
        await interaction.response.send_message(f"❌ Ce jeu existe déjà dans la base de données : **{name}**")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de l'ajout du jeu : {str(e)}")
        
# 📌 Supprimer un jeu
@bot.command(aliases=["Supprjeu"])
@commands.has_permissions(administrator=True)
async def supprjeu(ctx, name: str):
    try:
        cursor.execute("SELECT * FROM games WHERE LOWER(name) = %s", (name.lower(),))
        jeu = cursor.fetchone()

        if jeu:
            cursor.execute("DELETE FROM games WHERE LOWER(name) = %s", (name.lower(),))
            save_database()
            await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")
        else:
            await ctx.send(f"❌ Aucun jeu trouvé avec le nom '{name}'.")

    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la suppression du jeu : {str(e)}")
        
# 📌 Liste des jeux enregistrés
@bot.tree.command(name="listejeux")
async def listejeux(interaction: discord.Interaction):
    """ Affiche tous les jeux enregistrés, triés par ordre alphabétique. """
    try:
        cursor.execute("SELECT name FROM games ORDER BY LOWER(name) ASC")
        games = cursor.fetchall()

        if games:
            game_list = "\n".join([game[0].capitalize() for game in games])
            await interaction.response.send_message(f"🎮 **Liste des jeux enregistrés (triée A-Z) :**\n```{game_list}```")
        else:
            await interaction.response.send_message("❌ Aucun jeu enregistré.")

    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des jeux : {str(e)}")
        
# 📌 Recherche par nom (`/NomDuJeu`)
@bot.event
async def on_message(message):
    """ Recherche un jeu par son nom et affiche la fiche. """
    if message.author == bot.user:
        return

    if message.content.startswith("/"):
        jeu_nom = message.content[1:].strip().lower()

        try:
            conn.rollback()  # 🔥 Annule toute transaction en erreur
            cursor.execute("""
                SELECT name, release_date, price, type, duration, cloud_available, youtube_link, steam_link
                FROM games WHERE LOWER(name) LIKE %s
            """, (f"%{jeu_nom}%",))
            games_found = cursor.fetchall()

            if len(games_found) == 1:
                game_info = games_found[0]
                embed = discord.Embed(
                    title=f"🎮 **{game_info[0].capitalize()}**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
                embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
                embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
                embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
                embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
                embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
                embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)

                await message.channel.send(embed=embed)
            else:
                await bot.process_commands(message)

        except psycopg2.Error as e:
            await message.channel.send(f"❌ Erreur SQL : {str(e)}")

# 📌 Recherche par type (`/type`)
@bot.command(aliases=["Types", "Type"])
async def type(ctx, game_type: str = None):
    """ Affiche tous les jeux correspondant à un type donné. """
    if game_type is None:
        await ctx.send("❌ Utilisation correcte : `/type NomDuType`\nTape `/types` pour voir tous les types disponibles.")
        return

    game_type = game_type.lower().strip()
    cursor.execute("SELECT name, type FROM games")
    games_found = cursor.fetchall()

    matching_games = []

    for game_name, game_types in games_found:
        type_list = [t.strip().lower() for t in game_types.split(",")]  # Séparation des types
        if game_type in type_list:
            matching_games.append(game_name.capitalize())

    if matching_games:
        game_list = "\n".join(f"- {game}" for game in matching_games)
        await ctx.send(f"🎮 **Jeux trouvés pour le type '{game_type.capitalize()}':**\n```{game_list}```")
    else:
        await ctx.send(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")

@bot.command()
async def types(ctx):
    """ Affiche tous les types de jeux disponibles dans la base. """
    cursor.execute("SELECT DISTINCT type FROM games")
    types_found = cursor.fetchall()

    unique_types = set()  # Utilisation d'un ensemble pour éviter les doublons

    for row in types_found:
        types_list = row[0].lower().split(",")  # Séparation des types avec ","
        unique_types.update([t.strip().capitalize() for t in types_list])  # Suppression des espaces et mise en capitales

    if unique_types:
        type_list = "\n".join(f"- {t}" for t in sorted(unique_types))  # Trie et affichage propre
        await ctx.send(f"🎮 **Types de jeux disponibles :**\n```{type_list}```\nTape `!type NomDuType` pour voir les jeux correspondants.")
    else:
        await ctx.send("❌ Aucun type de jeu trouvé dans la base.")

class JeuButton(discord.ui.View):
    def __init__(self, jeu_nom):
        super().__init__(timeout=300)
        self.jeu_nom = jeu_nom
        self.add_item(discord.ui.Button(label=jeu_nom, style=discord.ButtonStyle.primary, custom_id=f"jeu:{jeu_nom.lower()}"))

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """ Gère le clic sur le nom du jeu pour afficher la fiche. """
    if interaction.data and "custom_id" in interaction.data:
        custom_id = interaction.data["custom_id"]
        if custom_id.startswith("jeu:"):
            jeu_nom = custom_id.split("jeu:")[1]

            cursor.execute("SELECT * FROM games WHERE LOWER(name) = %s", (jeu_nom,))
            game_info = cursor.fetchone()

            if game_info:
                embed = discord.Embed(title=f"🎮 {game_info[0].capitalize()}", color=discord.Color.blue())
                embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
                embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
                embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
                embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
                embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
                embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
                embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)

                await interaction.response.send_message(embed=embed, ephemeral=False)

# 📌 Propose un jeu aléatoire
@bot.tree.command(name="proposejeu")
async def proposejeu(interaction: discord.Interaction):
    """ Propose un jeu aléatoire """
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        await interaction.response.send_message(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?")
    else:
        await interaction.response.send_message("❌ Aucun jeu enregistré.")

# 📌 Propose un jeu aléatoire selon un type
@bot.tree.command(name="proposejeutype")
async def proposejeutype(interaction: discord.Interaction, game_type: str):
    """ Propose un jeu aléatoire basé sur un type donné """
    game_type = game_type.lower().strip()
    cursor.execute("SELECT name FROM games WHERE LOWER(type) LIKE %s", (f"%{game_type}%",))
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        await interaction.response.send_message(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?")
    else:
        await interaction.response.send_message(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")
        
# 📌 Commandes disponibles
@bot.tree.command(name="commandes")
async def commandes(interaction: discord.Interaction):
    """ Affiche la liste des commandes disponibles. """
    
    is_admin = interaction.user.guild_permissions.administrator

    public_commands = """
**📜 Commandes publiques :**
🔹 `/listejeux` → Affiche tous les jeux enregistrés (triés A-Z)  
🔹 `/types` → Affiche tous les types de jeux enregistrés  
🔹 `/type "TypeDeJeu"` → Affiche tous les jeux d'un type donné  
🔹 `/ask "NomDuJeu"` → Demande l'ajout d'un jeu  
🔹 `/proposejeu` → Propose un jeu aléatoire  
🔹 `/proposejeutype "TypeDeJeu"` → Propose un jeu d’un type donné  
"""

    admin_commands = """
**🔒 Commandes Admin :**
🔹 `/ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → Ajoute un jeu  
🔹 `/modifjeu "Nom" "Champ" "NouvelleValeur"` → Modifie un jeu  
🔹 `/demandes` → Affiche les jeux demandés  
🔹 `/supprdemande "NomDuJeu"` → Supprime une demande manuellement  
"""

    embed = discord.Embed(title="📜 Liste des commandes", color=discord.Color.blue())
    embed.add_field(name="📌 Instructions", value="Tape `/` suivi d'une lettre pour voir les commandes disponibles.", inline=False)
    embed.add_field(name="🔹 Commandes publiques", value=public_commands, inline=False)

    if is_admin:
        embed.add_field(name="🔒 Commandes Admin", value=admin_commands, inline=False)

    await interaction.response.send_message(embed=embed)
    
class JeuView(discord.ui.View):
    def __init__(self, jeu_nom):
        super().__init__(timeout=300)
        self.jeu_nom = jeu_nom

@bot.event
async def on_message(message):
    """ Auto-complétion des commandes en fonction de ce que l'utilisateur tape. """
    if message.author == bot.user or not message.content.startswith("/"):
        return  # Ignore les messages du bot et ceux qui ne commencent pas par "/"

    user_input = message.content.lower()[1:]  # Enlève le "/" et met en minuscule
    possible_commands = [cmd.name for cmd in bot.commands if cmd.name.startswith(user_input)]
    
    if possible_commands:
        suggestions = " | ".join(f"`/{cmd}`" for cmd in possible_commands)
        await message.channel.send(f"🔎 Suggestions : {suggestions}")

    await bot.process_commands(message)  # Permet aux autres commandes de fonctionner normalement

# Lancer le bot
bot.run(TOKEN)
