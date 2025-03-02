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
@bot.command()
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    try:
        cursor.execute(f"UPDATE games SET {field} = %s WHERE LOWER(name) = %s", (new_value, name.lower()))
        save_database()
        await ctx.send(f"✅ Jeu '{name}' mis à jour : **{field}** → {new_value}")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la modification du jeu : {str(e)}")

# 📌 Ajouter un jeu
@bot.command()
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
@bot.command()
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
@bot.command()
async def listejeux(ctx):
    try:
        cursor.execute("SELECT name FROM games")
        games = cursor.fetchall()
        if games:
            game_list = "\n".join([game[0].capitalize() for game in games])
            await ctx.send(f"🎮 **Liste des jeux enregistrés :**\n```{game_list}```")
        else:
            await ctx.send("❌ Aucun jeu enregistré.")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la récupération des jeux : {str(e)}")

# 📌 Recherche par nom (`!NomDuJeu`)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith("!"):
        jeu_nom = message.content[1:].strip().lower()
        cursor.execute("SELECT * FROM games WHERE LOWER(name) LIKE %s", (f"%{jeu_nom}%",))
        games_found = cursor.fetchall()
        if len(games_found) == 1:
            game_info = games_found[0]
            embed = discord.Embed(title=f"🎮 {game_info[1].capitalize()}", color=discord.Color.blue())
            embed.add_field(name="📅 Date de sortie", value=game_info[2], inline=False)
            embed.add_field(name="💰 Prix", value=game_info[3], inline=False)
            embed.add_field(name="🎮 Type", value=game_info[4].capitalize(), inline=False)
            await message.channel.send(embed=embed)
    await bot.process_commands(message)

# 📌 Recherche par type (`!type`)
@bot.command()
async def type(ctx, game_type: str):
    cursor.execute("SELECT name FROM games WHERE LOWER(type) LIKE %s", (f"%{game_type}%",))
    games_found = cursor.fetchall()
    if games_found:
        game_list = "\n".join([f"- {game[0].capitalize()}" for game in games_found])
        await ctx.send(f"🎮 **Jeux trouvés pour le type '{game_type.capitalize()}':**\n```{game_list}```")
    else:
        await ctx.send(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")

# 📌 Proposer un jeu aléatoire
@bot.command()
async def proposejeu(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()
    if games:
        jeu_choisi = random.choice(games)[0]
        await ctx.send(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?")
    else:
        await ctx.send("❌ Aucun jeu enregistré.")

# 📌 Commandes disponibles
@bot.command()
async def commandes(ctx):
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → (ADMIN) Ajoute un jeu  
🔹 `!supprjeu "Nom"` → (ADMIN) Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → (ADMIN) Modifie un jeu  
🔹 `!listejeux` → Affiche tous les jeux enregistrés  
🔹 `!type "TypeDeJeu"` → Affiche tous les jeux d'un type donné  
🔹 `!proposejeu` → Propose un jeu aléatoire  
🔹 `!commandes` → Affiche cette liste  
"""
    await ctx.send(commandes_list)

# Lancer le bot
bot.run(TOKEN)
