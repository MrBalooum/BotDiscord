import discord
from discord.ext import commands
import sqlite3
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

# Connexion à la base de données SQLite
DB_PATH = "games.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS games (
                    name TEXT PRIMARY KEY, 
                    release_date TEXT, 
                    price TEXT, 
                    type TEXT, 
                    duration TEXT, 
                    cloud_available TEXT, 
                    youtube_link TEXT, 
                    steam_link TEXT)''')
conn.commit()

# Liste pour suivre les derniers messages (bot + utilisateur)
last_messages = []

async def manage_message_lifetime(message, duration=60):
    """ Supprime les messages après un certain temps, sauf les 2 derniers """
    global last_messages

    await asyncio.sleep(duration)
    
    try:
        await message.delete()
    except discord.NotFound:
        pass  # Le message est déjà supprimé

    last_messages.append(message)
    if len(last_messages) > 2:
        old_message = last_messages.pop(0)
        try:
            await old_message.delete()
        except discord.NotFound:
            pass

def save_database():
    """ Sauvegarde la base de données pour éviter toute perte. """
    conn.commit()
    print("📂 Base de données sauvegardée avec succès.")

# 📌 Modifier un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    cursor.execute(f"UPDATE games SET {field} = ? WHERE LOWER(name) = ?", (new_value, name.lower()))
    save_database()
    message = await ctx.send(f"✅ Jeu '{name}' mis à jour : **{field}** → {new_value}")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Ajout d'un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def ajoutjeu(ctx, name: str, release_date: str, price: str, types: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    try:
        cursor.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                       (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link))
        save_database()
        message = await ctx.send(f"✅ Jeu '{name}' ajouté avec succès !")
    except sqlite3.IntegrityError:
        message = await ctx.send("❌ Ce jeu existe déjà dans la base de données !")
    except Exception as e:
        message = await ctx.send(f"❌ Erreur lors de l'ajout du jeu : {str(e)}")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Supprimer un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def supprjeu(ctx, name: str):
    cursor.execute("DELETE FROM games WHERE LOWER(name) = ?", (name.lower(),))
    save_database()
    message = await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Liste des jeux enregistrés
@bot.command()
async def listejeux(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()

    if games:
        game_list = "\n".join([game[0].capitalize() for game in games])
        message = await ctx.send(f"🎮 **Liste des jeux enregistrés :**\n```{game_list}```")
    else:
        message = await ctx.send("❌ Aucun jeu enregistré.")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Détection automatique d'un jeu avec `!nom du jeu`
@bot.event
async def on_message(message):
    """ Vérifie si un message correspond au nom d'un jeu et affiche la fiche. """
    if message.author == bot.user:
        return  # Empêche le bot de répondre à lui-même

    # Vérifier si le message commence par "!" et extraire le nom du jeu sans les espaces en trop
    if message.content.startswith("!"):
        jeu_nom = message.content[1:].strip().lower()  # Retire "!" et met en minuscules

        # Vérifier dans la base de données en ignorant la casse
        cursor.execute("SELECT * FROM games WHERE LOWER(name) = ?", (jeu_nom,))
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

            message_bot = await message.channel.send(embed=embed)

            # Suppression automatique après 60 sec, sauf les derniers messages (5 min)
            await manage_message_lifetime(message_bot)
            await manage_message_lifetime(message)

    await bot.process_commands(message)  # Permet aux autres commandes de fonctionner
nner

# 📌 Commande pour voir toutes les commandes
@bot.command()
async def commandes(ctx):
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → (ADMIN) Ajoute un jeu  
🔹 `!supprjeu "Nom"` → (ADMIN) Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → (ADMIN) Modifie un jeu  
🔹 `!listejeux` → Affiche tous les jeux  
🔹 `!commandes` → Affiche cette liste de commandes
"""
    message = await ctx.send(commandes_list)
    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# Lancer le bot
bot.run(TOKEN)
