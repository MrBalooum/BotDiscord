import discord
from discord.ext import commands
import sqlite3
import asyncio
import os
import random
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

# Fonction pour récupérer l'image d'un jeu depuis Steam
def get_steam_image(steam_link):
    try:
        if "store.steampowered.com" in steam_link:
            game_id = steam_link.split('/app/')[1].split('/')[0]
            return f"https://cdn.akamai.steamstatic.com/steam/apps/{game_id}/header.jpg"
    except:
        return None
    return None

# Fonction pour ajouter un jeu avec gestion des erreurs
@bot.command()
async def ajoutjeu(ctx, name: str, release_date: str, price: str, type: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    try:
        cursor.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                       (name.lower(), release_date, price, type, duration, cloud_available, youtube_link, steam_link))
        conn.commit()
        message = await ctx.send(f"✅ Jeu '{name}' ajouté avec succès !")
        await asyncio.sleep(600)
        await message.delete()
        await ctx.message.delete()
    except sqlite3.IntegrityError:
        await ctx.send("❌ Ce jeu existe déjà dans la base de données !")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'ajout du jeu : {str(e)}")

# Fonction pour supprimer un jeu
@bot.command()
async def supprjeu(ctx, name: str):
    cursor.execute("DELETE FROM games WHERE name = ?", (name.lower(),))
    conn.commit()
    message = await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")
    await asyncio.sleep(600)
    await message.delete()
    await ctx.message.delete()

# Fonction pour proposer un jeu aléatoire
@bot.command()
async def proposejeu(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()
    if games:
        jeu_choisi = random.choice(games)[0]
        await ctx.send(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?")
    else:
        await ctx.send("❌ Aucun jeu enregistré dans la base de données.")

# Auto-complétion des noms de jeux lorsque l'utilisateur tape une première lettre
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    cursor.execute("SELECT name FROM games WHERE name LIKE ?", (message.content.lower() + "%",))
    result = cursor.fetchall()
    
    if result:
        suggestions = ", ".join([game[0].capitalize() for game in result])
        await message.channel.send(f"🔎 Suggestions : {suggestions}")
    
    cursor.execute("SELECT * FROM games WHERE name = ?", (message.content.lower(),))
    game_info = cursor.fetchone()
    
    if game_info:
        embed = discord.Embed(title=game_info[0].capitalize(), color=discord.Color.blue())
        embed.add_field(name="Date de sortie", value=game_info[1], inline=True)
        embed.add_field(name="Prix", value=game_info[2], inline=True)
        embed.add_field(name="Type", value=game_info[3], inline=True)
        embed.add_field(name="Durée de vie", value=game_info[4], inline=True)
        embed.add_field(name="Disponible en Cloud", value=game_info[5], inline=True)
        embed.add_field(name="Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
        embed.add_field(name="Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)
        
        # Ajout de l'image du jeu via Steam si disponible
        steam_image = get_steam_image(game_info[7])
        if steam_image:
            embed.set_image(url=steam_image)

        bot_message = await message.channel.send(embed=embed)
        await asyncio.sleep(600)
        await bot_message.delete()
        await message.delete()
    else:
        await bot.process_commands(message)

# Fonction pour afficher la liste des jeux
@bot.command()
async def listejeux(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()
    if games:
        game_list = "\n".join([game[0].capitalize() for game in games])
        message = await ctx.send(f"🎮 **Liste des jeux enregistrés :**\n{game_list}")
        await asyncio.sleep(600)
        await message.delete()
        await ctx.message.delete()
    else:
        await ctx.send("❌ Aucun jeu enregistré dans la base de données.")

# Lancer le bot
bot.run(TOKEN)
