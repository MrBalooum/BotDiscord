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

import psycopg2

# Récupération de l'URL de connexion PostgreSQL depuis Railway
DATABASE_URL = os.getenv("DATABASE_URL")

# Connexion à la base PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode="require", client_encoding="UTF8")
cursor = conn.cursor()

# Création de la table "games" si elle n'existe pas encore
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


def save_database():
    """ Sauvegarde immédiate des changements dans PostgreSQL """
    conn.commit()
    print("📂 Base de données sauvegardée avec succès sur Railway.")
    os.fsync(conn)  # 🔥 Force l'écriture des données sur le disque
    print("📂 Base de données sauvegardée avec succès.")

# 📌 Modifier un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def modifjeu(ctx, name: str, field: str, new_value: str):
    try:
        cursor.execute(f"UPDATE games SET {field} = %s WHERE LOWER(name) = %s", (new_value, name.lower()))
        save_database()  # 🔥 Sauvegarde immédiate
        await ctx.send(f"✅ Jeu '{name}' mis à jour : **{field}** → {new_value}")
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de la modification du jeu : {str(e)}")

# 📌 Ajout d'un jeu (réservé aux admins)
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
    except psycopg2.Error as e:
        await ctx.send(f"❌ Erreur PostgreSQL lors de l'ajout : {e.pgcode} - {e.pgerror}")
    except Exception as e:
        await ctx.send(f"❌ Erreur inattendue : {str(e)}")
        
# 📌 Supprimer un jeu (réservé aux admins)
@bot.command()
@commands.has_permissions(administrator=True)
async def supprjeu(ctx, name: str):
    try:
        cursor.execute("DELETE FROM games WHERE LOWER(name) = %s", (name.lower(),))
        save_database()  # 🔥 Sauvegarde immédiate
        await ctx.send(f"🗑️ Jeu '{name}' supprimé avec succès !")
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

# 📌 Recherche partielle par nom (`!NomDuJeu`)
@bot.event
async def on_message(message):
    """ Recherche un jeu par son nom partiel et affiche la fiche. """
    if message.author == bot.user:
        return

    if message.content.startswith("!"):
        jeu_nom = message.content[1:].strip().lower()

        cursor.execute("SELECT * FROM games WHERE LOWER(name) LIKE %s", (f"%{jeu_nom}%",))
        games_found = cursor.fetchall()

        if len(games_found) == 1:
            game_info = games_found[0]
            embed = discord.Embed(title=f"🎮 {game_info[0].capitalize()}", color=discord.Color.blue())
            embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
            embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
            embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
            embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
            embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
            embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
            embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)
            await message.channel.send(embed=embed)

        elif len(games_found) > 1:
            game_list = "\n".join([f"- {game[0].capitalize()}" for game in games_found])
            await message.channel.send(f"🔍 Plusieurs jeux trouvés :\n```{game_list}```\nTape le nom exact avec `!NomDuJeu` pour voir la fiche.")

    await bot.process_commands(message)

# 📌 Recherche par type (`!Type`)
@bot.command()
async def type(ctx, game_type: str):
    """ Affiche tous les jeux correspondant à un type donné. """
    game_type = game_type.lower().strip()

    cursor.execute("SELECT name FROM games WHERE LOWER(type) LIKE ?", (f"%{game_type}%",))
    games_found = cursor.fetchall()

    if games_found:
        game_list = "\n".join([f"- {game[0].capitalize()}" for game in games_found])
        await ctx.send(f"🎮 **Jeux trouvés pour le type '{game_type.capitalize()}':**\n```{game_list}```")
    else:
        await ctx.send(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")
        
# 📌 Proposer un jeu aléatoire avec un bouton pour voir sa fiche
class JeuButton(discord.ui.View):
    def __init__(self, game_name):
        super().__init__(timeout=300)
        self.game_name = game_name

    @discord.ui.button(label="Voir la fiche", style=discord.ButtonStyle.primary)
    async def show_game_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT * FROM games WHERE LOWER(name) = ?", (self.game_name.lower(),))
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

@bot.command()
async def proposejeu(ctx):
    """ Sélectionne un jeu aléatoire et propose de voir sa fiche. """
    cursor.execute("SELECT name FROM games")
    games = cursor.fetchall()

    if games:
        jeu_choisi = random.choice(games)[0]
        view = JeuButton(jeu_choisi)
        await ctx.send(f"🎮 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?", view=view)
    else:
        await ctx.send("❌ Aucun jeu enregistré.")

@bot.command()
async def commandes(ctx):
    """ Affiche la liste des commandes disponibles. """
    commandes_list = """
**📜 Liste des commandes disponibles :**
🔹 `!ajoutjeu "Nom" "Date" "Prix" "Type(s)" "Durée" "Cloud" "Lien YouTube" "Lien Steam"` → (ADMIN) Ajoute un jeu  
🔹 `!supprjeu "Nom"` → (ADMIN) Supprime un jeu  
🔹 `!modifjeu "Nom" "Champ" "NouvelleValeur"` → (ADMIN) Modifie un jeu  
🔹 `!listejeux` → Affiche tous les jeux enregistrés  
🔹 `!type "TypeDeJeu"` → Affiche tous les jeux d'un type donné  
🔹 `!proposejeu` → Propose un jeu aléatoire avec sa fiche  
🔹 `!commandes` → Affiche cette liste de commandes  
🔹 **Recherche d’un jeu :** Tape `!NomDuJeu` (ex: `!The Witcher 3`) pour voir sa fiche complète  
"""
    await ctx.send(commandes_list)

# Lancer le bot
bot.run(TOKEN)
