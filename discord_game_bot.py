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

        # Initialisation du menu déroulant
        super().__init__(
            placeholder="📌 Sélectionne une commande...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        """ Quand on sélectionne une commande, elle est suggérée dans la barre de message (sans être envoyée). """
        selected_command = self.values[0]

        # Empêche le bot d'envoyer un message visible
        await interaction.response.defer()

        # Simule la suggestion de la commande dans la barre de message
        await interaction.followup.send(
            f"**Tape ta commande :** `{selected_command}` et appuie sur `Entrée` !",
            ephemeral=True  # Message visible uniquement par l'utilisateur
        )

class CommandesView(discord.ui.View):
    def __init__(self, is_admin):
        super().__init__(timeout=120)  # Les boutons restent actifs 2 minutes
        self.add_item(CommandesDropdown(is_admin))

def save_database():
    """ Sauvegarde immédiate des changements dans PostgreSQL. """
    conn.commit()
    print("📂 Base de données sauvegardée avec succès sur Railway.")

# 📌 Demander un jeu
@bot.command(aliases=["Ask", "Demande", "demande"])
async def ask(ctx, *, game_name: str):
    """ Ajoute une demande de jeu avec confirmation """
    user_id = ctx.author.id
    username = ctx.author.name
    game_name = game_name.strip().capitalize()

    try:
        # Vérifier si le jeu est déjà demandé
        cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
        existing = cursor.fetchone()

        if existing:
            await ctx.send(f"❌ **{game_name}** est déjà dans la liste des demandes.")
            return

        # Ajouter la demande
        cursor.execute("INSERT INTO game_requests (user_id, username, game_name) VALUES (%s, %s, %s)", (user_id, username, game_name))
        conn.commit()

        await ctx.send(f"📩 **{game_name}** a été ajouté à la liste des demandes par {username} !")
    
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'ajout de la demande : {str(e)}")


# 📌 Voir la liste des demandes (ADMIN)
@bot.command(aliases=["Demandes", "ListeDemandes"])
@commands.has_permissions(administrator=True)
async def demandes(ctx):
    """ Affiche la liste des jeux demandés avec l'utilisateur qui l'a demandé """
    cursor.execute("SELECT username, game_name FROM game_requests ORDER BY date DESC")
    requests = cursor.fetchall()

    if requests:
        request_list = "\n".join([f"- **{r[1]}** (demandé par {r[0]})" for r in requests])
        await ctx.send(f"📜 **Liste des jeux demandés :**\n```{request_list}```")
    else:
        await ctx.send("📭 **Aucune demande en attente.**")

# 📌 Supprimer une demande manuellement (ADMIN)
@bot.command(aliases=["Supprdemande", "Retirerdemande"])
@commands.has_permissions(administrator=True)
async def supprdemande(ctx, game_name: str):
    """ Supprime une demande de jeu de la liste """
    cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
    demande = cursor.fetchone()

    if demande:
        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
        conn.commit()
        await ctx.send(f"🗑️ La demande pour **{game_name.capitalize()}** a été supprimée.")
    else:
        await ctx.send(f"❌ Aucun jeu trouvé dans la liste des demandes sous le nom '{game_name}'.")


# 📌 Modifier un jeu
@bot.command(aliases=["modiffjeu", "Modifjeu", "Modiffjeu"])
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    """ Modifie un champ spécifique d'un jeu """
    try:
        # Normalisation du nom du jeu
        name = name.strip().lower()

        # Vérifier si le jeu existe en utilisant LIKE
        cursor.execute("SELECT * FROM games WHERE LOWER(name) LIKE %s", (f"%{name}%",))
        jeu = cursor.fetchone()

        if not jeu:
            await ctx.send(f"❌ Aucun jeu trouvé avec le nom '{name.capitalize()}'. Vérifie l'orthographe ou utilise `!listejeux`.")
            return

        # Vérifier que le champ existe
        valid_fields = ["release_date", "price", "type", "duration", "cloud_available", "youtube_link", "steam_link"]
        if field.lower() not in valid_fields:
            await ctx.send(f"❌ Le champ `{field}` n'est pas valide. Champs disponibles : {', '.join(valid_fields)}")
            return

        # Modifier le champ
        query = f"UPDATE games SET {field} = %s WHERE LOWER(name) LIKE %s"
        cursor.execute(query, (new_value, f"%{name}%"))
        conn.commit()

        await ctx.send(f"✅ Jeu '{jeu[0].capitalize()}' mis à jour : **{field}** → {new_value}")

    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la modification du jeu : {str(e)}")

# 📌 Ajouter un jeu
@bot.command(aliases=["AjoutJeu", "ajoutJeu"])
@commands.has_permissions(administrator=True)
async def ajoutjeu(ctx, name: str, release_date: str, price: str, types: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    """ Ajoute un jeu à la liste et le supprime des demandes s'il existait dans !ask """
    try:
        # Ajout du jeu dans la base
        cursor.execute(
            "INSERT INTO games (name, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
            (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link)
        )
        save_database()

        # Supprimer la demande associée
        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (name.lower(),))
        conn.commit()

        await ctx.send(f"✅ **{name}** ajouté avec succès et retiré des demandes !")

    except psycopg2.IntegrityError:
        await ctx.send(f"❌ Ce jeu existe déjà dans la base de données : **{name}**")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'ajout du jeu : {str(e)}")

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
@bot.command(aliases=["Listejeux", "listejeu", "Listejeu"])
async def listejeux(ctx):
    """ Affiche tous les jeux enregistrés, triés par ordre alphabétique. """
    try:
        cursor.execute("SELECT name FROM games ORDER BY LOWER(name) ASC")
        games = cursor.fetchall()

        if games:
            game_list = "\n".join([game[0].capitalize() for game in games])
            await ctx.send(f"🎮 **Liste des jeux enregistrés (triée A-Z) :**\n```{game_list}```")
        else:
            await ctx.send("❌ Aucun jeu enregistré.")

    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la récupération des jeux : {str(e)}")

# 📌 Recherche par nom (`!NomDuJeu`)
@bot.event
async def on_message(message):
    """ Recherche un jeu par son nom et affiche la fiche. """
    if message.author == bot.user:
        return

    if message.content.startswith("!"):
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

# 📌 Recherche par type (`!type`)
@bot.command(aliases=["Types", "Type"])
async def type(ctx, game_type: str = None):

    """ Affiche tous les jeux correspondant à un type donné. """
    if game_type is None:
        await ctx.send("❌ Utilisation correcte : `!type NomDuType`\nTape `!types` pour voir tous les types disponibles.")
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
    def __init__(self, game_name):
        super().__init__(timeout=120)
        self.game_name = game_name

    @discord.ui.button(label="Voir la fiche du jeu", style=discord.ButtonStyle.primary)
    async def show_game_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        """ Affiche la fiche du jeu quand on clique sur le bouton. """
        cursor.execute("SELECT * FROM games WHERE LOWER(name) = %s", (self.game_name.lower(),))
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

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Jeu introuvable.", ephemeral=True)

@bot.command(aliases=["ProposeJeu", "ProposerJeu"])
async def proposejeu(ctx):
    """ Propose un jeu aléatoire et permet de voir sa fiche en cliquant sur son nom. """
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        await ctx.send(f"🎮 Pourquoi ne pas essayer **[{jeu_choisi.capitalize()}](https://game-info/{jeu_choisi.replace(' ', '_')})** ?")
    else:
        await ctx.send("❌ Aucun jeu enregistré.")

@bot.command(name="proposejeutype", aliases=["ProposeJeuType", "proposerJeuType", "ProposerJeuType"])
async def proposejeutype(ctx, game_type: str = None):
    """ Propose un jeu aléatoire basé sur un type donné et permet d'afficher sa fiche. """
    
    if not game_type:
        await ctx.send("❌ Utilisation correcte : `!proposejeutype NomDuType`\nTape `!types` pour voir tous les types disponibles.")
        return

    game_type = game_type.lower().strip()

    cursor.execute("SELECT name FROM games WHERE LOWER(type) LIKE %s", (f"%{game_type}%",))
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        await ctx.send(f"🎮 Pourquoi ne pas essayer **[{jeu_choisi.capitalize()}](https://game-info/{jeu_choisi.replace(' ', '_')})** ?")
    else:
        await ctx.send(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.\nTape `!types` pour voir les types existants.")

def get_steam_image(steam_link):
    """ Récupère l'image d'un jeu depuis Steam. """
    try:
        if "store.steampowered.com" in steam_link:
            game_id = steam_link.split('/app/')[1].split('/')[0]
            return f"https://cdn.akamai.steamstatic.com/steam/apps/{game_id}/header.jpg"
    except:
        return None
    return None

# 📌 Commandes disponibles
@bot.command(aliases=["Commande", "commande", "Commandes"])
async def commandes(ctx):
    """ Affiche la liste des commandes disponibles, en cachant celles des admins pour les non-admins. """
    
    # Vérifier si l'utilisateur est un admin
    is_admin = ctx.author.guild_permissions.administrator
    view = CommandesView(is_admin)

    # Commandes accessibles à tous
    public_commands = """
**📜 Commandes publiques :**
🔹 `!listejeux` → Affiche tous les jeux enregistrés (triés A-Z)  
🔹 `!types` → Affiche tous les types de jeux enregistrés  
🔹 `!type "TypeDeJeu"` → Affiche tous les jeux d'un type donné  
🔹 `!ask "NomDuJeu"` → Demande l'ajout d'un jeu (les admins peuvent voir cette liste avec `!demandes`)  
🔹 `!proposejeu` → Propose un jeu aléatoire  
🔹 `!proposejeutype "TypeDeJeu"` → Propose un jeu aléatoire selon un type spécifique  
🔹 **Recherche d’un jeu :** Tape `!NomDuJeu` (ex: `!The Witcher 3`) pour voir sa fiche complète  
"""

    # Commandes réservées aux admins
    admin_commands = """
**🔒 Commandes Admin :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → Ajoute un jeu  
🔹 `!supprjeu "Nom"` → Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → Modifie un jeu  
🔹 `!demandes` → Affiche la liste des jeux demandés par les utilisateurs  
🔹 `!createtable` → Crée la table des demandes (si elle n'existe pas encore)  
"""

    embed = discord.Embed(title="📜 Liste des commandes", color=discord.Color.blue())
    embed.add_field(
        name="📌 Instructions",
        value="Sélectionne une commande dans le menu ci-dessous. Elle s'écrira automatiquement dans ta barre de message.",
        inline=False
    )
    embed.add_field(name="📂 Commandes publiques", value=public_commands, inline=False)

    if is_admin:
        embed.add_field(name="🔒 Commandes Admin", value=admin_commands, inline=False)

    await ctx.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    """ Vérifie si un message contient un jeu cliqué et affiche la fiche. """
    if message.author == bot.user:
        return

    # Vérifier si le message contient un lien de jeu
    if "https://game-info/" in message.content:
        jeu_nom = message.content.split("https://game-info/")[1].replace("_", " ").strip().lower()

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

            await message.channel.send(embed=embed)

    await bot.process_commands(message)
    
# Lancer le bot
bot.run(TOKEN)
