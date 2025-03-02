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
conn = sqlite3.connect("games.db")
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
    
    # Vérifie si le message existe encore avant de le supprimer
    try:
        await message.delete()
    except discord.NotFound:
        pass  # Le message est déjà supprimé

    # Met à jour la liste des derniers messages
    last_messages.append(message)
    if len(last_messages) > 2:
        old_message = last_messages.pop(0)
        try:
            await old_message.delete()
        except discord.NotFound:
            pass  # Message déjà supprimé

# 📌 Modifier un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    valid_fields = ["release_date", "price", "type", "duration", "cloud_available", "youtube_link", "steam_link"]
    
    if field not in valid_fields:
        message = await ctx.send(f"❌ Champ invalide ! Tu peux modifier : {', '.join(valid_fields)}")
    else:
        cursor.execute(f"UPDATE games SET {field} = ? WHERE name = ?", (new_value, name.lower()))
        conn.commit()
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
        conn.commit()
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
    cursor.execute("SELECT * FROM games WHERE name = ?", (name.lower(),))
    game_exists = cursor.fetchone()

    if game_exists:
        cursor.execute("DELETE FROM games WHERE name = ?", (name.lower(),))
        conn.commit()
        message = await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")
    else:
        message = await ctx.send(f"❌ Jeu '{name}' introuvable.")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Liste des jeux enregistrés
@bot.command()
async def listejeux(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()
    
    if games:
        game_list = "\n".join([game[0].capitalize() for game in games])
        message = await ctx.send(f"🎮 **Liste des jeux enregistrés :**\n{game_list}")
    else:
        message = await ctx.send("❌ Aucun jeu enregistré.")

    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# 📌 Commande pour voir toutes les commandes
@bot.command()
async def commandes(ctx):
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → (ADMIN) Ajoute un jeu  
🔹 `!supprjeu "Nom"` → (ADMIN) Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → (ADMIN) Modifie un jeu  
🔹 `!listejeux` → Affiche tous les jeux  
🔹 `!proposejeu` → Propose un jeu interactif  
🔹 `!type` → Affiche tous les types de jeux enregistrés  
🔹 `!typejeux "Type"` → Affiche tous les jeux d'un type donné  
🔹 `!commandes` → Affiche cette liste de commandes
"""
    message = await ctx.send(commandes_list)
    await manage_message_lifetime(message)
    await manage_message_lifetime(ctx.message)

# Lancer le bot
bot.run(TOKEN)
