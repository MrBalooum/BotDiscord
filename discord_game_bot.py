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

# Fonction pour récupérer l'image d'un jeu depuis Steam
def get_steam_image(steam_link):
    try:
        if "store.steampowered.com" in steam_link:
            game_id = steam_link.split('/app/')[1].split('/')[0]
            return f"https://cdn.akamai.steamstatic.com/steam/apps/{game_id}/header.jpg"
    except:
        return None
    return None

# 📌 Ajout d'un jeu avec plusieurs types
@bot.command()
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

    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# 📌 Supprimer un jeu
@bot.command()
async def supprjeu(ctx, name: str):
    cursor.execute("SELECT * FROM games WHERE name = ?", (name.lower(),))
    game_exists = cursor.fetchone()

    if game_exists:
        cursor.execute("DELETE FROM games WHERE name = ?", (name.lower(),))
        conn.commit()
        message = await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")
    else:
        message = await ctx.send(f"❌ Jeu '{name}' introuvable.")

    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# 📌 Liste des types disponibles
@bot.command()
async def type(ctx):
    cursor.execute("SELECT DISTINCT type FROM games")
    types = cursor.fetchall()
    if types:
        type_list = set()
        for t in types:
            type_list.update(t[0].split(","))
        message = await ctx.send(f"📌 **Types de jeux disponibles :**\n{', '.join(sorted(type_list))}")
    else:
        message = await ctx.send("❌ Aucun type enregistré.")

    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# 📌 Afficher les jeux d'un type spécifique
@bot.command()
async def typejeux(ctx, game_type: str):
    cursor.execute("SELECT name FROM games WHERE type LIKE ?", (f"%{game_type.lower()}%",))
    games = cursor.fetchall()

    if games:
        game_list = "\n".join([game[0].capitalize() for game in games])
        message = await ctx.send(f"🎮 **Jeux du type '{game_type.capitalize()}' :**\n{game_list}")
    else:
        message = await ctx.send(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")

    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# 📌 Proposer un jeu avec interaction
class JeuButton(discord.ui.View):
    def __init__(self, game_name):
        super().__init__(timeout=60)
        self.game_name = game_name

    @discord.ui.button(label="Voir la fiche", style=discord.ButtonStyle.primary)
    async def show_game_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT * FROM games WHERE name = ?", (self.game_name,))
        game_info = cursor.fetchone()

        if game_info:
            embed = discord.Embed(title=game_info[0].capitalize(), color=discord.Color.blue())
            embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=True)
            embed.add_field(name="💰 Prix", value=game_info[2], inline=True)
            embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=True)
            embed.add_field(name="⏳ Durée", value=game_info[4], inline=True)
            embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=True)
            embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
            embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)

            steam_image = get_steam_image(game_info[7])
            if steam_image:
                embed.set_image(url=steam_image)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Le jeu n'a pas été trouvé.", ephemeral=True)

@bot.command()
async def proposejeu(ctx):
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()
    if games:
        jeu_choisi = random.choice(games)[0]
        view = JeuButton(jeu_choisi)
        message = await ctx.send(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?", view=view)
    else:
        message = await ctx.send("❌ Aucun jeu enregistré.")

    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# 📌 Commande pour voir toutes les commandes
@bot.command()
async def commandes(ctx):
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → Ajoute un jeu  
🔹 `!supprjeu "Nom"` → Supprime un jeu  
🔹 `!listejeux` → Affiche tous les jeux  
🔹 `!proposejeu` → Propose un jeu interactif  
🔹 `!type` → Affiche tous les types de jeux enregistrés  
🔹 `!typejeux "Type"` → Affiche tous les jeux d'un type donné  
🔹 `!commandes` → Affiche cette liste de commandes
"""
    message = await ctx.send(commandes_list)
    await asyncio.sleep(60)
    await message.delete()
    await ctx.message.delete()

# Lancer le bot
bot.run(TOKEN)
