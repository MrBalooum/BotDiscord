import discord
from discord.ext import commands
import sqlite3
import asyncio

# Configuration du bot
TOKEN = os.getenv("TOKEN")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Connexion à la base de données SQLite
conn = sqlite3.connect("games.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS games (
                    name TEXT PRIMARY KEY, 
                    description TEXT, 
                    release_date TEXT, 
                    price TEXT, 
                    youtube_link TEXT)''')
conn.commit()

# Fonction pour ajouter un jeu avec gestion des erreurs
@bot.command()
async def ajoutjeu(ctx, name: str, description: str, release_date: str, price: str, youtube_link: str):
    try:
        cursor.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?)", (name.lower(), description, release_date, price, youtube_link))
        conn.commit()
        message = await ctx.send(f"✅ Jeu '{name}' ajouté avec succès !")
        await asyncio.sleep(600)  # Supprime après 10 minutes (600 secondes)
        await message.delete()
        await ctx.message.delete()
    except sqlite3.IntegrityError:
        await ctx.send("❌ Ce jeu existe déjà dans la base de données !")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'ajout du jeu : {str(e)}")

# Fonction pour modifier la description d'un jeu
@bot.command()
async def modifjeu(ctx, name: str, new_description: str):
    cursor.execute("UPDATE games SET description = ? WHERE name = ?", (new_description, name.lower()))
    conn.commit()
    message = await ctx.send(f"✅ Description de '{name}' mise à jour !")
    await asyncio.sleep(600)
    await message.delete()
    await ctx.message.delete()

# Fonction pour chercher un jeu sans préfixe
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    cursor.execute("SELECT * FROM games WHERE name = ?", (message.content.lower(),))
    result = cursor.fetchone()
    
    if result:
        embed = discord.Embed(title=result[0].capitalize(), color=discord.Color.blue())
        embed.add_field(name="Description", value=result[1], inline=False)
        embed.add_field(name="Date de sortie", value=result[2], inline=True)
        embed.add_field(name="Prix sur Steam", value=result[3], inline=True)
        embed.add_field(name="Gameplay YouTube", value=result[4], inline=False)
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
