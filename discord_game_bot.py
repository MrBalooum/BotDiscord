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

def save_database():
    """ Sauvegarde immédiate des changements dans PostgreSQL. """
    conn.commit()
    print("📂 Base de données sauvegardée avec succès sur Railway.")

# 📌 Modifier un jeu
@bot.command(aliases=["modiffjeu", "Modifjeu", "Modiffjeu"])
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    """ Modifie un champ spécifique d'un jeu """
    try:
        # Normalisation du nom du jeu
        name = name.strip().lower()

        # Vérifier si le jeu existe
        cursor.execute("SELECT * FROM games WHERE LOWER(name) = %s", (name,))
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
        query = f"UPDATE games SET {field} = %s WHERE LOWER(name) = %s"
        cursor.execute(query, (new_value, name))
        conn.commit()

        await ctx.send(f"✅ Jeu '{name.capitalize()}' mis à jour : **{field}** → {new_value}")

    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la modification du jeu : {str(e)}")


# 📌 Ajouter un jeu
@bot.command(aliases=["AjoutJeu", "Ajoutjeu"])
@commands.has_permissions(administrator=True)
async def ajoutjeu(ctx, name: str, release_date: str, price: str, types: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    try:
        cursor.execute(
            "INSERT INTO games (name, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
            (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link)
        )
        save_database()
        await ctx.send(f"✅ Jeu '{name}' ajouté avec succès !")
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

    # Vérifie si le message commence par "!" (évite les erreurs)
    if message.content.startswith("!"):
        jeu_nom = message.content[1:].strip().lower()

        cursor.execute("""
            SELECT name, release_date, price, type, duration, cloud_available, youtube_link, steam_link
            FROM games WHERE LOWER(name) LIKE %s
        """, (f"%{jeu_nom}%",))

        games_found = cursor.fetchall()

        if len(games_found) == 1:
            game_info = games_found[0]

            embed = discord.Embed(
                title=f"🎮 **{game_info[0].capitalize()}**",  # Titre en gras
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

# 📌 Proposer un jeu aléatoire
@bot.command
async def proposejeu(ctx):
    """ Sélectionne un jeu aléatoire et propose de voir sa fiche. """
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        
        cursor.execute("""
            SELECT name, release_date, price, type, duration, cloud_available, youtube_link, steam_link
            FROM games WHERE LOWER(name) = %s
        """, (jeu_choisi.lower(),))

        game_info = cursor.fetchone()

        if game_info:
            steam_image_url = get_steam_image(game_info[7]) if game_info[7] else None

            embed = discord.Embed(
                title=f"🎮 **{game_info[0].capitalize()}**",  # Titre agrandi
                color=discord.Color.blue()
            )
            embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
            embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
            embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
            embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
            embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
            embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
            embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)

            if steam_image_url:
                embed.set_image(url=steam_image_url)  # Ajoute l'image Steam

            await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Aucun jeu enregistré.")

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
    """ Affiche la liste des commandes disponibles. """
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → (ADMIN) Ajoute un jeu  
🔹 `!supprjeu "Nom"` → (ADMIN) Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → (ADMIN) Modifie un jeu  
🔹 `!listejeux` → Affiche tous les jeux enregistrés (triés A-Z)  
🔹 `!types` → Affiche tous les types de jeux enregistrés  
🔹 `!type "TypeDeJeu"` → Affiche tous les jeux d'un type donné  
🔹 `!proposejeu` → Propose un jeu aléatoire  
🔹 `!commandes` → Affiche cette liste  
🔹 **Recherche d’un jeu :** Tape `!NomDuJeu` (ex: `!The Witcher 3`) pour voir sa fiche complète  
"""
    await ctx.send(commandes_list)

# Lancer le bot
bot.run(TOKEN)
