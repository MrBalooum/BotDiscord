import discord
from discord.ext import commands
import psycopg2
import asyncio
import os
import random
import re
from discord import app_commands

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

# Création (ou mise à jour) de la table "games"
cursor.execute('''CREATE TABLE IF NOT EXISTS games (
    id SERIAL PRIMARY KEY,
    nom TEXT UNIQUE,
    release_date TEXT,
    price TEXT,
    type TEXT,
    duration TEXT,
    cloud_available TEXT,
    youtube_link TEXT,
    steam_link TEXT
)''')
conn.commit()

# Création de la table "user_favorites" (pour les favoris par utilisateur)
cursor.execute('''CREATE TABLE IF NOT EXISTS user_favorites (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    game TEXT,
    UNIQUE(user_id, game)
)''')
conn.commit()

# Mettre "Aucun" dans la colonne commentaire pour tous les jeux déjà en base
cursor.execute("UPDATE games SET commentaire = 'Aucun' WHERE commentaire IS NULL OR commentaire = ''")
conn.commit()

# S'assurer que la colonne "date_ajout" existe (si elle n'existe pas, on l'ajoute)
try:
    cursor.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    conn.commit()
except Exception as e:
    print("Erreur lors de l'ajout de la colonne date_ajout :", e)

# Vérification de la structure de la table pour renommer "name" en "nom" si nécessaire
try:
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='games'")
    columns = [row[0] for row in cursor.fetchall()]
    if 'name' in columns and 'nom' not in columns:
        cursor.execute("ALTER TABLE games RENAME COLUMN name TO nom")
        conn.commit()
        print("Colonne 'name' renommée en 'nom'")
except Exception as e:
    print("Erreur lors de la vérification de la structure de la table games:", e)

# Création de la table "game_requests" pour la commande /ask
cursor.execute('''CREATE TABLE IF NOT EXISTS game_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    game_name TEXT UNIQUE,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

# Création de la table "game_problems" (pour les problèmes signalés)
cursor.execute('''CREATE TABLE IF NOT EXISTS game_problems (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    game TEXT,
    message TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

# Ajout de la colonne "Commentaire" si elle n'existe pas
cursor.execute("""
    ALTER TABLE games ADD COLUMN IF NOT EXISTS commentaire TEXT
""")
conn.commit()

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()  # Synchronisation des commandes slash
        print("✅ Commandes slash synchronisées avec Discord !")
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes slash : {e}")
    print(f"🤖 Bot connecté en tant que {bot.user}")

def save_database():
    """Sauvegarde immédiate des changements dans PostgreSQL."""
    conn.commit()
    print("📂 Base de données sauvegardée avec succès.")

############################################
#         COMMANDES SLASH
############################################

# Commande pour afficher la fiche d'un jeu
@bot.tree.command(name="fiche", description="Affiche la fiche détaillée d'un jeu")
async def fiche(interaction: discord.Interaction, game: str):
    game_query = game.strip().lower()
    try:
        cursor.execute("""
            SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link, commentaire
            FROM games
            WHERE TRIM(LOWER(nom)) = %s
        """, (game_query,))
        game_info = cursor.fetchone()
        if game_info:
            embed = discord.Embed(
                title=f"🎮 {game_info[0].capitalize()}",
                color=discord.Color.blue()
            )
            embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
            embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
            embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
            embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
            embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
            embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
            embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)
            if game_info[8]:
                embed.add_field(name="ℹ️ Commentaire", value=game_info[8], inline=False)
            
            view = discord.ui.View()
            class FavButton(discord.ui.Button):
                def __init__(self):
                    super().__init__(style=discord.ButtonStyle.primary, emoji="⭐", label="Ajouter aux favoris")
                async def callback(self, interaction: discord.Interaction):
                    try:
                        cursor.execute("INSERT INTO user_favorites (user_id, game) VALUES (%s, %s) ON CONFLICT DO NOTHING", (interaction.user.id, game_info[0]))
                        conn.commit()
                        await interaction.response.send_message(f"✅ **{game_info[0].capitalize()}** ajouté à vos favoris !", ephemeral=True)
                    except Exception as e:
                        conn.rollback()
                        await interaction.response.send_message(f"❌ Erreur lors de l'ajout aux favoris : {str(e)}", ephemeral=True)
            view.add_item(FavButton())
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé avec le nom '{game_query}'.", ephemeral=True)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur SQL: {str(e)}", ephemeral=True)
        
@fiche.autocomplete("game")
async def fiche_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower().strip()
    try:
        cursor.execute("""
            SELECT nom FROM games
            WHERE LOWER(nom) LIKE %s
            ORDER BY nom ASC
            LIMIT 25
        """, (f"%{current_lower}%",))
        results = cursor.fetchall()
        suggestions = [row[0].capitalize() for row in results]
        return [app_commands.Choice(name=name, value=name) for name in suggestions]
    except Exception as e:
        conn.rollback()
        return []

@bot.event
async def on_member_join(member):
    guild = member.guild
    # Rechercher (ou créer) le rôle "UserAccess"
    role = discord.utils.get(guild.roles, name="UserAccess")
    if role is None:
        role = await guild.create_role(name="UserAccess")
    # Attribuer le rôle au nouveau membre
    await member.add_roles(role)
    # Définir le nom du salon basé sur le pseudo du membre (sans ajout de suffixe)
    channel_name = member.name.lower().replace(" ", "-")
    # Si un salon avec ce nom existe déjà, le supprimer pour éviter le suffixe "-0"
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if existing_channel:
        await existing_channel.delete(reason="Création d'un nouveau salon personnel pour le membre.")
    # Définir les permissions : seul le membre et le rôle "UserAccess" peuvent voir et écrire dans le salon
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    # Créer le salon textuel avec le nom sans suffixe et ajouter l'ID du membre dans le topic pour le retrouver plus tard
    user_channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        topic=f"Salon personnel de {member.name}. ID: {member.id}"
    )
    # Liste des commandes autorisées pour l'utilisateur
    commandes = ("/fiche | /Listejeux | /Dernier | /Style | "
                 "/Proposejeu | /Proposejeutype | /Type | /Ask | "
                 "/Fav | /Favori | /Unfav | /Probleme")
    # Message de bienvenue personnalisé
    welcome_message = (
        f"Bienvenue {member.mention} sur ton salon personnel !\n"
        "Voici les commandes dont tu disposes pour profiter pleinement du serveur :\n"
        f"{commandes}\n\n"
        "N'oublie pas de consulter le salon #rules pour connaître les règles du serveur.\n"
        "Bienvenue et amuse-toi bien !"
    )
    await user_channel.send(welcome_message)

@bot.event
async def on_member_remove(member):
    guild = member.guild
    # Parcourir tous les salons textuels du serveur et supprimer celui associé au membre
    for channel in guild.text_channels:
        if channel.topic and f"ID: {member.id}" in channel.topic:
            await channel.delete(reason=f"Le membre {member.name} a quitté le serveur")

@bot.tree.command(name="ask", description="Demande l'ajout d'un jeu")
async def ask(interaction: discord.Interaction, game_name: str):
    user_id = interaction.user.id
    username = interaction.user.name
    game_name_clean = game_name.strip().capitalize()
    try:
        cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name_clean.lower(),))
        existing = cursor.fetchone()
        if existing:
            await interaction.response.send_message(f"❌ **{game_name_clean}** est déjà dans la liste des demandes.", ephemeral=True)
            return
        cursor.execute("INSERT INTO game_requests (user_id, username, game_name) VALUES (%s, %s, %s)", (user_id, username, game_name_clean))
        conn.commit()
        await interaction.response.send_message(f"📩 **{game_name_clean}** a été ajouté à la liste des demandes par {username} !")
        general_channel = discord.utils.get(interaction.guild.text_channels, name="général")
        if general_channel:
            await general_channel.send(f"📣 Le jeu **{game_name_clean}** a été demandé par **{username}**.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de l'ajout de la demande : {str(e)}", ephemeral=True)

from discord import Permissions, Object

GUILD_ID = 1343310341655892028  # ID de ton serveur

@bot.tree.command(
    name="supprdemande",
    description="Supprime une demande de jeu ou un problème signalé (ADMIN)",
    guild=Object(id=GUILD_ID),
    default_member_permissions=Permissions(administrator=True)
)
async def supprdemande(interaction: discord.Interaction, name: str, type: str):
    type_clean = type.strip().lower()
    try:
        if type_clean == "probleme":
            cursor.execute("SELECT user_id, game FROM game_problems WHERE LOWER(game) = %s", (name.lower(),))
            problem_data = cursor.fetchone()
            if problem_data:
                user_id, game_name = problem_data 
                cursor.execute("DELETE FROM game_problems WHERE LOWER(game) = %s", (name.lower(),))
                conn.commit()
                general_channel = discord.utils.get(interaction.guild.text_channels, name="général")
                tech_channel = discord.utils.get(interaction.guild.text_channels, name="mrbalooum")
                if "(Problème technique)" in game_name:
                    cleaned_game_name = game_name.replace("(Problème technique)", "").strip()
                    user = await bot.fetch_user(user_id)
                    if user:
                        await user.send(f"🎉 **Ton problème technique sur {cleaned_game_name} a été résolu !**")
                else:
                    if general_channel:
                        await general_channel.send(f"✅ **Le problème sur {game_name} a été résolu !**")
                    if tech_channel:
                        await tech_channel.send(f"🎮 **{game_name} (Problème jeu résolu)**\n**Date :** {interaction.created_at.strftime('%d/%m/%Y %H:%M')}")
                await interaction.response.send_message(f"✅ Le problème sur **{game_name}** a été supprimé avec succès.")
            else:
                await interaction.response.send_message(f"❌ Aucun problème trouvé pour **{name.capitalize()}**.", ephemeral=True)
        elif type_clean == "demande":
            cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s RETURNING game_name", (name.lower(),))
            deleted_request = cursor.fetchone()
            conn.commit()
            if deleted_request:
                await interaction.response.send_message(f"✅ La demande pour **{deleted_request[0].capitalize()}** a été supprimée avec succès.")
            else:
                await interaction.response.send_message(f"❌ Aucune demande trouvée pour **{name.capitalize()}**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Type invalide. Utilisez 'demande' ou 'probleme'.", ephemeral=True)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la suppression : {str(e)}", ephemeral=True)

@supprdemande.autocomplete("type")
async def supprdemande_type_autocomplete(interaction: discord.Interaction, current: str):
    options = ["demande", "probleme"]
    return [app_commands.Choice(name=opt.capitalize(), value=opt) for opt in options if current.lower() in opt]

@supprdemande.autocomplete("name")
async def supprdemande_name_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.strip().lower()
    try:
        cursor.execute("""
            SELECT DISTINCT game FROM game_problems 
            WHERE LOWER(game) LIKE %s 
            ORDER BY game ASC 
            LIMIT 25
        """, (f"%{current_lower}%",))
        results = cursor.fetchall()
        if not results:
            return []
        return [app_commands.Choice(name=row[0].capitalize(), value=row[0]) for row in results]
    except Exception as e:
        conn.rollback()
        return []

@bot.tree.command(
    name="supprjeu",
    description="Supprime un jeu (ADMIN)",
    guild=Object(id=GUILD_ID),
    default_member_permissions=Permissions(administrator=True)
)
async def supprjeu(interaction: discord.Interaction, name: str):
    try:
        name_clean = name.strip().lower()
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s", (f"%{name_clean}%",))
        jeu = cursor.fetchone()
        if jeu:
            cursor.execute("DELETE FROM games WHERE LOWER(nom) = %s", (name_clean,))
            save_database()
            await interaction.response.send_message(f"🗑️ Jeu '{name.capitalize()}' supprimé avec succès !")
            general_channel = discord.utils.get(interaction.guild.text_channels, name="général")
            if general_channel:
                await general_channel.send(f"📣 **{name.capitalize()}** n'est plus disponible !")
        else:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé avec le nom '{name}'.", ephemeral=True)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la suppression du jeu : {str(e)}", ephemeral=True)
        
@supprjeu.autocomplete("name")
async def supprjeu_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.strip().lower()
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
        results = cursor.fetchall()
        suggestions = [row[0] for row in results]
        return [app_commands.Choice(name=s.capitalize(), value=s) for s in suggestions]
    except Exception as e:
        conn.rollback()
        return []

@bot.tree.command(
    name="modifjeu",
    description="Modifie un champ d'un jeu (ADMIN)",
    guild=Object(id=GUILD_ID),
    default_member_permissions=Permissions(administrator=True)
)
async def modifjeu(interaction: discord.Interaction, name: str, champ: str, nouvelle_valeur: str = ""):
    try:
        name_clean = name.strip().lower()
        champ_clean = champ.strip().lower()
        mapping = {
            "nom": "nom",
            "sortie": "release_date",
            "prix": "price",
            "type": "type",
            "durée": "duration",
            "duree": "duration",
            "cloud": "cloud_available",
            "youtube": "youtube_link",
            "steam": "steam_link",
            "commentaire": "commentaire"
        }
        if champ_clean not in mapping:
            await interaction.response.send_message(
                f"❌ Champ invalide. Utilisez : {', '.join(mapping.keys())}.",
                ephemeral=True
            )
            return
        new_value = nouvelle_valeur.strip() if nouvelle_valeur else "Aucun"
        actual_field = mapping[champ_clean]
        cursor.execute(f"UPDATE games SET {actual_field} = %s WHERE LOWER(nom) LIKE %s", (new_value, f"%{name_clean}%"))
        conn.commit()
        await interaction.response.send_message(f"✅ {champ.capitalize()} de **{name.capitalize()}** mis à jour : {new_value}")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la modification : {str(e)}", ephemeral=True)

@modifjeu.autocomplete("name")
async def modifjeu_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.strip().lower()
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
        results = cursor.fetchall()
        return [app_commands.Choice(name=row[0].capitalize(), value=row[0]) for row in results]
    except Exception as e:
        conn.rollback()
        return []
        
@modifjeu.autocomplete("champ")
async def modifjeu_champ_autocomplete(interaction: discord.Interaction, current: str):
    options = {
        "nom": "nom",
        "sortie": "release_date",
        "prix": "price",
        "type": "type",
        "durée": "duration",
        "cloud": "cloud_available",
        "youtube": "youtube_link",
        "steam": "steam_link",
        "commentaire": "commentaire"
    }
    current_lower = current.strip().lower()
    return [
        app_commands.Choice(name=key.capitalize(), value=value)
        for key, value in options.items()
        if current_lower in key
    ]

############################################
# Nouvelles commandes pour les favoris
############################################

@bot.tree.command(name="fav", description="Ajoute un jeu aux favoris")
async def fav(interaction: discord.Interaction, name: str):
    try:
        name_clean = name.strip().lower()
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s", (f"%{name_clean}%",))
        jeu = cursor.fetchone()
        if not jeu:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé correspondant à '{name}'.", ephemeral=True)
            return
        try:
            cursor.execute("INSERT INTO user_favorites (user_id, game) VALUES (%s, %s)", (interaction.user.id, jeu[0]))
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()
            await interaction.response.send_message(f"❌ Le jeu **{jeu[0].capitalize()}** est déjà dans vos favoris.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ **{jeu[0].capitalize()}** a été ajouté à vos favoris !")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de l'ajout aux favoris : {str(e)}", ephemeral=True)

@fav.autocomplete("name")
async def fav_autocomplete(interaction: discord.Interaction, current: str):
    try:
        current_lower = current.strip().lower()
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s", (f"%{current_lower}%",))
        games = cursor.fetchall()
        cursor.execute("SELECT game FROM user_favorites WHERE user_id = %s", (interaction.user.id,))
        favs = cursor.fetchall()
        fav_list = {row[0].lower() for row in favs}
        suggestions = [game[0] for game in games if game[0].lower() not in fav_list]
        suggestions = sorted(suggestions, key=str.lower)
        return [app_commands.Choice(name=s.capitalize(), value=s) for s in suggestions][:25]
    except Exception as e:
        conn.rollback()
        return []

@bot.tree.command(name="favoris", description="Affiche votre liste de favoris")
async def favoris(interaction: discord.Interaction):
    try:
        cursor.execute("SELECT game FROM user_favorites WHERE user_id = %s ORDER BY game ASC", (interaction.user.id,))
        favs = cursor.fetchall()
        if not favs:
            await interaction.response.send_message("❌ Vous n'avez aucun jeu favori.", ephemeral=True)
            return
        fav_list = "\n".join(f"• {row[0].capitalize()}" for row in favs)
        embed = discord.Embed(title="🌟 Vos favoris", description=fav_list, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des favoris : {str(e)}", ephemeral=True)

@bot.tree.command(name="unfav", description="Retire un jeu de vos favoris")
async def unfav(interaction: discord.Interaction, name: str):
    try:
        name_clean = name.strip().lower()
        cursor.execute("SELECT game FROM user_favorites WHERE user_id = %s AND LOWER(game) = %s", (interaction.user.id, name_clean))
        fav = cursor.fetchone()
        if not fav:
            await interaction.response.send_message(f"❌ Le jeu **{name}** n'est pas dans vos favoris.", ephemeral=True)
            return
        cursor.execute("DELETE FROM user_favorites WHERE user_id = %s AND LOWER(game) = %s", (interaction.user.id, name_clean))
        conn.commit()
        await interaction.response.send_message(f"✅ **{name.capitalize()}** a été retiré de vos favoris.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la suppression des favoris : {str(e)}", ephemeral=True)

@unfav.autocomplete("name")
async def unfav_autocomplete(interaction: discord.Interaction, current: str):
    try:
        current_lower = current.strip().lower()
        cursor.execute("SELECT game FROM user_favorites WHERE user_id = %s", (interaction.user.id,))
        favs = cursor.fetchall()
        suggestions = [row[0] for row in favs if current_lower in row[0].lower()]
        suggestions = sorted(set(suggestions), key=str.lower)
        return [app_commands.Choice(name=s.capitalize(), value=s) for s in suggestions][:25]
    except Exception as e:
        conn.rollback()
        return []

############################################
#         CLASSE DE PAGINATION
############################################

class PaginationView(discord.ui.View):
    def __init__(self, embeds, timeout=120):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="Précédent", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()

bot.run(TOKEN)
