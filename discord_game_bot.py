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

from discord import app_commands

# Commande pour afficher la fiche d'un jeu
@bot.tree.command(name="fiche", description="Affiche la fiche détaillée d'un jeu")
async def fiche(interaction: discord.Interaction, game: str):
    """Affiche la fiche d'un jeu dont le nom est fourni."""
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
        
import asyncio

@bot.event
async def on_member_join(member):
    guild = member.guild

    print(f"🔹 Nouveau membre : {member.name}")

    # Vérification du rôle UserAccess
    role = discord.utils.get(guild.roles, name="UserAccess")
    if role is None:
        role = await guild.create_role(name="UserAccess")
        print("✅ Rôle UserAccess créé")

    # Ajouter le rôle au membre
    await member.add_roles(role)
    print(f"✅ Rôle UserAccess ajouté à {member.name}")

    # Définition du nom du salon
    channel_name = member.name.lower().replace(" ", "-")

    # Vérifier si un salon avec ce nom existe déjà et le supprimer
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if existing_channel:
        print(f"🗑️ Suppression de l'ancien salon {existing_channel.name}")
        await existing_channel.delete(reason="Création d'un nouveau salon personnel.")

    # Définition des permissions du salon
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }

    # Création du salon textuel
    try:
        user_channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            topic=f"Salon personnel de {member.name}. ID: {member.id}"
        )
        print(f"✅ Salon créé : {user_channel.name}")
    except Exception as e:
        print(f"❌ Erreur lors de la création du salon : {e}")
        return  # On arrête ici si la création a échoué

    # Attendre 2 secondes pour éviter un bug de Discord
    await asyncio.sleep(2)

    # Test des permissions pour voir si le bot peut envoyer un message
    if user_channel.permissions_for(guild.me).send_messages:
        print(f"📢 Le bot peut envoyer des messages dans {user_channel.name}")
    else:
        print(f"🚨 Le bot N'A PAS la permission d'envoyer des messages dans {user_channel.name} !")

    # Message de bienvenue
    welcome_message = (
        f"Bienvenue {member.mention} sur ton salon personnel !\n"
        "Voici les commandes dont tu disposes pour profiter pleinement du serveur :\n"
        "/fiche | /Listejeux | /Dernier | /Style | "
        "/Proposejeu | /Proposejeutype | /Type | /Ask | "
        "/Fav | /Favori | /Unfav | /Probleme\n\n"
        "N'oublie pas de consulter le salon #rules pour connaître les règles du serveur.\n"
        "Bienvenue et amuse-toi bien !"
    )

    try:
        await user_channel.send(welcome_message)
        print(f"✅ Message de bienvenue envoyé à {member.name} dans {user_channel.name}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi du message de bienvenue : {e}")


@bot.event
async def on_member_remove(member):
    guild = member.guild

    print(f"🔹 {member.name} a quitté le serveur")

    # Recherche du salon basé sur l'ID dans le topic
    for channel in guild.text_channels:
        if channel.topic and f"ID: {member.id}" in channel.topic:
            print(f"🔍 Salon trouvé pour suppression : {channel.name}")
            try:
                await channel.delete(reason=f"Le membre {member.name} a quitté le serveur")
                print(f"🗑️ Salon {channel.name} supprimé")
            except Exception as e:
                print(f"❌ Erreur lors de la suppression du salon {channel.name} : {e}")
            return  # On arrête la boucle dès qu'on trouve le bon salon

    print(f"⚠️ Aucun salon trouvé pour {member.name}")

@bot.tree.command(name="ask", description="Demande l'ajout d'un jeu")
async def ask(interaction: discord.Interaction, game_name: str):
    """Demande à ajouter un jeu à la base."""
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

@bot.tree.command(name="supprdemande", description="Supprime une demande de jeu ou un problème signalé (ADMIN)")
@commands.has_permissions(administrator=True)
async def supprdemande(interaction: discord.Interaction, name: str, type: str):
    """Supprime une demande ou un problème et informe les utilisateurs de la résolution."""
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
                    # ✅ Problème technique -> MP à l’utilisateur
                    cleaned_game_name = game_name.replace("(Problème technique)", "").strip()
                    user = await bot.fetch_user(user_id)
                    if user:
                        await user.send(f"🎉 **Ton problème technique sur {cleaned_game_name} a été résolu !**")
                else:
                    # ✅ Problème de jeu -> Message dans #général et #mrbalooum
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
    """Autocomplétion du paramètre 'type' avec 'demande' et 'probleme'."""
    options = ["demande", "probleme"]
    return [app_commands.Choice(name=opt.capitalize(), value=opt) for opt in options if current.lower() in opt]

@supprdemande.autocomplete("name")
async def supprdemande_name_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion des noms de jeux ayant des problèmes signalés ou des demandes."""
    current_lower = current.strip().lower()

    try:
        # Récupérer les problèmes et les demandes qui matchent avec la saisie de l'utilisateur
        cursor.execute("""
            SELECT DISTINCT game FROM game_problems WHERE LOWER(game) LIKE %s
            UNION
            SELECT DISTINCT game_name FROM game_requests WHERE LOWER(game_name) LIKE %s
            ORDER BY game ASC LIMIT 25
        """, (f"%{current_lower}%", f"%{current_lower}%"))
        
        results = cursor.fetchall()

        if not results:
            return []

        # Formater les résultats pour Discord
        return [app_commands.Choice(name=row[0].capitalize(), value=row[0]) for row in results]

    except Exception as e:
        print(f"❌ Erreur lors de l'autocomplétion : {e}")
        return []

@bot.tree.command(name="supprjeu", description="Supprime un jeu (ADMIN)")
@commands.has_permissions(administrator=True)
async def supprjeu(interaction: discord.Interaction, name: str):
    """
    Supprime un jeu de la base de données.
    Utilisation : /supprjeu "Nom du jeu"
    """
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
    """Propose les noms de jeux présents dans la bibliothèque pour le paramètre 'name'."""
    try:
        current_lower = current.strip().lower()
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
        results = cursor.fetchall()
        suggestions = [row[0] for row in results]
        return [app_commands.Choice(name=s.capitalize(), value=s) for s in suggestions]
    except Exception as e:
        conn.rollback()
        return []


@bot.tree.command(name="modifjeu", description="Modifie un champ d'un jeu (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def modifjeu(interaction: discord.Interaction, name: str, champ: str, nouvelle_valeur: str = ""):
    """
    Modifie un seul champ d'un jeu existant.
    
    Si le champ modifié est "commentaire" et que rien n'est saisi, le jeu aura "Aucun" comme valeur.
    """
    try:
        name_clean = name.strip().lower()
        champ_clean = champ.strip().lower()

        # Liste des champs autorisés pour modification
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

        # Si le champ est "commentaire" et que l'utilisateur ne met rien, on le remplace par "Aucun"
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
    """Propose des noms de jeux présents dans la bibliothèque pour le paramètre 'name'."""
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
    """Autocomplétion pour le champ à modifier."""
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
    """
    Ajoute un jeu aux favoris de l'utilisateur.
    Utilisation : /fav "Nom du jeu"
    """
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
    """Propose uniquement les jeux non déjà dans les favoris de l'utilisateur."""
    try:
        current_lower = current.strip().lower()
        # Récupérer les jeux dans la bibliothèque
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s", (f"%{current_lower}%",))
        games = cursor.fetchall()
        # Récupérer les jeux déjà en favoris pour l'utilisateur
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
    """
    Affiche la liste des jeux favoris de l'utilisateur.
    """
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
    """
    Retire un jeu de vos favoris.
    Utilisation : /unfav "Nom du jeu"
    """
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
    """Propose uniquement les jeux déjà dans vos favoris."""
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

@bot.tree.command(name="ajoutjeu", description="Ajoute un jeu (ADMIN)")
@commands.has_permissions(administrator=True)
async def ajoutjeu(
    interaction: discord.Interaction, 
    name: str, release_date: str, price: str, types: str, 
    duration: str, cloud_available: str, youtube_link: str, steam_link: str, 
    commentaire: str = "Aucun"
):
    """Ajoute un nouveau jeu avec un commentaire et envoie la fiche dans le salon 'général'."""
    try:
        cursor.execute(
            "INSERT INTO games (nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link, commentaire) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", 
            (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link, commentaire)
        )
        save_database()

        # Supprime la demande associée s'il y en avait une
        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (name.lower(),))
        conn.commit()

        # Récupérer les infos du jeu ajouté
        cursor.execute("""
            SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link, commentaire
            FROM games 
            WHERE LOWER(nom) = %s
        """, (name.lower(),))
        game_info = cursor.fetchone()

        embed = discord.Embed(title=f"🎮 {game_info[0].capitalize()}", color=discord.Color.blue())
        embed.add_field(name="📅 Date de sortie", value=game_info[1], inline=False)
        embed.add_field(name="💰 Prix", value=game_info[2], inline=False)
        embed.add_field(name="🎮 Type", value=game_info[3].capitalize(), inline=False)
        embed.add_field(name="⏳ Durée", value=game_info[4], inline=False)
        embed.add_field(name="☁️ Cloud disponible", value=game_info[5], inline=False)
        embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({game_info[6]})", inline=False)
        embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({game_info[7]})", inline=False)
        embed.add_field(name="ℹ️ Commentaire", value=game_info[8], inline=False)

        await interaction.response.send_message(f"✅ **{name.capitalize()}** ajouté avec succès et retiré des demandes !")

        general_channel = discord.utils.get(interaction.guild.text_channels, name="général")
        if general_channel:
            await general_channel.send(f"📣 **{name.capitalize()}** vient d'être ajouté !", embed=embed)

    except psycopg2.IntegrityError:
        conn.rollback()
        await interaction.response.send_message(f"❌ Ce jeu existe déjà dans la base de données : **{name}**", ephemeral=True)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de l'ajout du jeu : {str(e)}", ephemeral=True)

############################################
# NOUVELLE COMMANDE POUR AJOUTER PLUSIEURS JEUX
############################################

import asyncio
import re

@bot.tree.command(name="ajoutjeux", description="Ajoute plusieurs jeux à la fois (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def ajoutjeux(interaction: discord.Interaction, games: str):
    """
    Ajoute plusieurs jeux à partir d'un bloc de texte.
    Chaque jeu doit être défini par exactement 8 valeurs entre guillemets :
    "Nom" "Date de sortie" "Prix" "Type" "Durée" "Cloud" "Lien YouTube" "Lien Steam"

    Exemple de bloc :
    /ajoutjeu "High on Life" "13 décembre 2022" "36.99" "FPS, Aventure" "10h" "Non" "https://..." "https://..."
    /ajoutjeu "Planet Of Lana" "23 mai 2023" "19,99 €" "2D, Chill, Histoire" "5h" "Non" "https://..." "https://..."
    """
    pattern = r'"(.*?)"'
    # Extrait toutes les valeurs entre guillemets dans le bloc
    matches = re.findall(pattern, games)
    total = len(matches)
    if total % 8 != 0:
        await interaction.response.send_message(
            f"❌ Erreur : le nombre total de valeurs extraites est {total}, "
            "et ce n'est pas un multiple de 8. Vérifiez le format.",
            ephemeral=True
        )
        return

    added_games = []
    errors = []

    # On répond d'abord au slash command pour éviter le "Interaction Failed"
    await interaction.response.send_message("⏳ Traitement en cours...", ephemeral=True)

    general_channel = discord.utils.get(interaction.guild.text_channels, name="général")

    for i in range(0, total, 8):
        nom, date_sortie, prix, type_jeu, duree, cloud, lien_yt, lien_steam = matches[i:i+8]
        try:
            cursor.execute(
                "INSERT INTO games (nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (nom.lower(), date_sortie, prix, type_jeu.lower(), duree, cloud, lien_yt, lien_steam)
            )
            conn.commit()
            added_games.append(nom)

            # Si on a trouvé le salon "général", on y envoie la fiche du jeu
            if general_channel:
                embed = discord.Embed(title=f"🎮 {nom.capitalize()}", color=discord.Color.blue())
                embed.add_field(name="📅 Date de sortie", value=date_sortie, inline=False)
                embed.add_field(name="💰 Prix", value=prix, inline=False)
                embed.add_field(name="🎮 Type", value=type_jeu.capitalize(), inline=False)
                embed.add_field(name="⏳ Durée", value=duree, inline=False)
                embed.add_field(name="☁️ Cloud disponible", value=cloud, inline=False)
                embed.add_field(name="▶️ Gameplay YouTube", value=f"[Voir ici]({lien_yt})", inline=False)
                if lien_steam.strip():
                    embed.add_field(name="🛒 Page Steam", value=f"[Voir sur Steam]({lien_steam})", inline=False)

                await general_channel.send(f"📣 **{nom.capitalize()}** vient d'être ajouté !", embed=embed)
                # Attendre 3 secondes avant d'envoyer le prochain
                await asyncio.sleep(3)

        except Exception as e:
            conn.rollback()
            errors.append(f"Erreur pour '{nom}': {str(e)}")

    # Récapitulatif final
    response = ""
    if added_games:
        response += f"✅ Jeux ajoutés : {', '.join(added_games)}\n"
    if errors:
        response += "❌ Erreurs :\n" + "\n".join(errors)

    if not response.strip():
        response = "Aucun jeu ajouté et aucune erreur détectée."

    # Envoie un message récapitulatif dans le canal "privé" de l'interaction
    # (celui qui a tapé la commande verra ce message)
    await interaction.followup.send(response, ephemeral=True)

@bot.tree.command(name="listejeux", description="Affiche infos Bundle et liste des jeux (15 par page)")
async def listejeux(interaction: discord.Interaction):
    """Envoie 2 messages : le premier avec les infos du bundle, le second avec la liste paginée des jeux."""
    try:
        # Récupérer les infos du Bundle
        cursor.execute("SELECT price, duration FROM games")
        data = cursor.fetchall()
        total_games = len(data)
        total_price = 0.0
        total_time = 0
        for row in data:
            price_str, duration_str = row
            p_match = re.findall(r"[\d\.,]+", price_str)
            if p_match:
                p = float(p_match[0].replace(",", "."))
                total_price += p
            t_match = re.findall(r"[\d\.,]+", duration_str)
            if t_match:
                t = float(t_match[0].replace(",", "."))
                total_time += int(round(t))

        # Création du header avec chaque info sur une ligne
        bundle_info = (
            "**🎮 Jeux dans le Bundle :** " + str(total_games) + "\n" +
            "**💶 Prix total :** " + f"{total_price:.2f} €" + "\n" +
            "**⏳ Temps total de jeu :** " + str(total_time) + " heures"
        )
        await interaction.response.send_message(bundle_info)

        # Récupérer la liste des jeux
        cursor.execute("SELECT nom FROM games ORDER BY LOWER(nom) ASC")
        games = cursor.fetchall()
        if not games:
            await interaction.followup.send("❌ Aucun jeu enregistré.")
            return
        game_names = [game[0].replace("||", "").strip().capitalize() for game in games]
        pages = [game_names[i:i+15] for i in range(0, len(game_names), 15)]
        embeds = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"🎮 Liste des jeux (Page {idx}/{len(pages)})",
                color=discord.Color.blue()
            )
            embed.description = "\n".join(f"• {name}" for name in page)
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            view = PaginationView(embeds)
            await interaction.followup.send(embed=embeds[0], view=view)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des jeux : {str(e)}", ephemeral=True)

############################################
# Nouvelle commande publique: /probleme
############################################

# Commande pour signaler un problème
@bot.tree.command(name="probleme", description="Signale un problème pour un jeu ou un problème technique")
async def probleme(interaction: discord.Interaction, game: str, message: str, type_probleme: str):
    """Signale un problème pour un jeu ou un problème technique."""
    try:
        game_clean = game.strip().lower()
        type_clean = type_probleme.strip().lower()
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s", (f"%{game_clean}%",))
        jeu = cursor.fetchone()

        if not jeu:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé correspondant à '{game}'.", ephemeral=True)
            return

        jeu_nom = jeu[0].capitalize()
        date_heure = interaction.created_at.strftime('%d/%m/%Y %H:%M')

        if type_clean == "jeu":
            cursor.execute(
                "INSERT INTO game_problems (user_id, username, game, message) VALUES (%s, %s, %s, %s)",
                (interaction.user.id, interaction.user.name, jeu_nom, message)
            )
            conn.commit()

            general_channel = discord.utils.get(interaction.guild.text_channels, name="général")
            tech_channel = discord.utils.get(interaction.guild.text_channels, name="mrbalooum")

            if general_channel:
                await general_channel.send(f"🚨 **{jeu_nom} (Problème jeu)** ! (Signalé par {interaction.user.name} à {date_heure})")

            if tech_channel:
                await tech_channel.send(f"🎮 **{jeu_nom} (Problème jeu)**\n**Utilisateur :** {interaction.user.name}\n**Message :** {message}\n**Date :** {date_heure}")

            await interaction.response.send_message(f"✅ Problème signalé pour **{jeu_nom}** : {message}")

        elif type_clean == "technique":
            # 🔥 **Ajout dans game_problems pour qu’il apparaisse dans /demandes et /supprdemande**
            cursor.execute(
                "INSERT INTO game_problems (user_id, username, game, message) VALUES (%s, %s, %s, %s)",
                (interaction.user.id, interaction.user.name, f"{jeu_nom} (Problème technique)", message)
            )
            conn.commit()

            tech_channel = discord.utils.get(interaction.guild.text_channels, name="mrbalooum")
            if tech_channel:
                await tech_channel.send(f"🔧 **{jeu_nom} (Problème technique)**\n**Utilisateur :** {interaction.user.name}\n**Message :** {message}\n**Date :** {date_heure}")
            await interaction.response.send_message(f"✅ Problème technique signalé pour **{jeu_nom}**")

        else:
            await interaction.response.send_message("❌ Type de problème invalide. Utilisez 'jeu' ou 'technique'.", ephemeral=True)

    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la signalisation du problème : {str(e)}", ephemeral=True)

@probleme.autocomplete("game")
@probleme.autocomplete("type_probleme")
async def probleme_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion pour 'game' et 'type_probleme'."""

    param_name = None
    if interaction.data and "options" in interaction.data:
        param_name = interaction.data["options"][-1]["name"]  # Récupère le paramètre en cours

    if param_name == "game":
        current_lower = current.strip().lower()
        try:
            cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
            results = cursor.fetchall()
            return [app_commands.Choice(name=row[0].capitalize(), value=row[0]) for row in results]
        except Exception as e:
            conn.rollback()
            return []

    elif param_name == "type_probleme":
        return [
            app_commands.Choice(name="Jeu", value="jeu"),
            app_commands.Choice(name="Technique", value="technique")
        ]

############################################
# Modification de /demandes pour afficher 2 messages
############################################

@bot.tree.command(name="demandes", description="Affiche les demandes et problèmes (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def demandes(interaction: discord.Interaction):
    """
    Affiche deux messages distincts :
      1) Demandes de jeux (table game_requests)
      2) Problèmes signalés (table game_problems)
    """
    try:
        # Récupérer les demandes de jeux
        cursor.execute("SELECT username, game_name, date FROM game_requests ORDER BY date DESC")
        requests_data = cursor.fetchall()
        if requests_data:
            demandes_msg = "\n".join(f"- **{r[1]}** (demandé par {r[0]} le {r[2].strftime('%d/%m %H:%M')})" for r in requests_data)
        else:
            demandes_msg = "Aucune demande de jeu."

        # Récupérer les problèmes signalés
        cursor.execute("SELECT username, game, message, date FROM game_problems ORDER BY date DESC")
        problems_data = cursor.fetchall()
        if problems_data:
            problemes_msg = "\n".join(f"- **{r[1]}** (signalé par {r[0]} le {r[3].strftime('%d/%m %H:%M')}) : {r[2]}" for r in problems_data)
        else:
            problemes_msg = "Aucun problème signalé."

        # Envoyer deux messages séparés
        await interaction.response.send_message("**Demandes de jeux :**\n" + demandes_msg)
        await interaction.followup.send("**Problèmes signalés :**\n" + problemes_msg)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des demandes : {str(e)}", ephemeral=True)

@bot.tree.command(name="dernier", description="Affiche les 10 derniers jeux ajoutés")
async def dernier(interaction: discord.Interaction):
    """Affiche les 10 derniers jeux ajoutés à la base."""
    try:
        cursor.execute("SELECT nom, date_ajout FROM games ORDER BY date_ajout DESC LIMIT 10")
        derniers = cursor.fetchall()
        if derniers:
            description = "\n".join(
                f"- **{jeu[0].capitalize()}** ajouté le {jeu[1].strftime('%d/%m/%Y')}" for jeu in derniers
            )
            embed = discord.Embed(
                title="🆕 Derniers jeux ajoutés",
                description=description,
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Aucun jeu enregistré.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des derniers jeux : {str(e)}", ephemeral=True)

@bot.tree.command(name="proposejeu", description="Propose un jeu aléatoire avec sa fiche")
async def proposejeu(interaction: discord.Interaction):
    """Propose un jeu aléatoire et affiche sa fiche complète."""
    try:
        cursor.execute("SELECT nom FROM games")
        games = cursor.fetchall()
        if games:
            jeu_choisi = random.choice(games)[0]
            cursor.execute("""
                SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link
                SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link, commentaire
                FROM games WHERE LOWER(nom) = %s
            """, (jeu_choisi.lower(),))
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
                if game_info[8]:
                    embed.add_field(name="ℹ️ Commentaire", value=game_info[8], inline=False)
                await interaction.response.send_message(f"🎲 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?", embed=embed)
            else:
                await interaction.response.send_message("❌ Erreur lors de la récupération de la fiche du jeu.")
        else:
            await interaction.response.send_message("❌ Aucun jeu enregistré.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la proposition du jeu : {str(e)}", ephemeral=True)

@bot.tree.command(name="proposejeutype", description="Propose un jeu aléatoire d'un type donné avec sa fiche")
async def proposejeutype(interaction: discord.Interaction, game_type: str):
    """Propose un jeu aléatoire d'un type précis et affiche sa fiche complète."""
    try:
        game_type = game_type.lower().strip()
        cursor.execute("SELECT nom, type FROM games")
        games_found = cursor.fetchall()
        matching_games = []
        for nom, types in games_found:
            type_list = [t.strip().lower() for t in types.split(",")]
            if game_type in type_list:
                matching_games.append(nom)
        if matching_games:
            jeu_choisi = random.choice(matching_games)
            cursor.execute("""
                SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link
                SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link, commentaire
                FROM games WHERE LOWER(nom) = %s
            """, (jeu_choisi.lower(),))
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
                if game_info[8]:
                    embed.add_field(name="ℹ️ Commentaire", value=game_info[8], inline=False)
                await interaction.response.send_message(f"🎲 Pourquoi ne pas essayer **{jeu_choisi.capitalize()}** ?", embed=embed)
            else:
                await interaction.response.send_message("❌ Erreur lors de la récupération de la fiche du jeu.")
        else:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé pour le type '{game_type.capitalize()}'.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la proposition du jeu par type : {str(e)}", ephemeral=True)

@bot.tree.command(name="style", description="Affiche tous les types de jeux disponibles")
async def style(interaction: discord.Interaction):
    """Affiche la liste de tous les types de jeux disponibles."""
    try:
        cursor.execute("SELECT DISTINCT type FROM games")
        types_found = cursor.fetchall()
        unique_types = set()
        for row in types_found:
            for t in row[0].split(","):
                t_clean = t.strip()
                if t_clean:
                    unique_types.add(t_clean.capitalize())
        if unique_types:
            type_list = "\n".join(f"- {t}" for t in sorted(unique_types))
            embed = discord.Embed(
                title="🎮 Types de jeux disponibles",
                description=type_list,
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Aucun type de jeu trouvé dans la base.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des types : {str(e)}", ephemeral=True)

# Nouvelle commande /type : affiche tous les jeux d'un type choisi
@bot.tree.command(name="type", description="Affiche tous les jeux d'un type choisi")
async def type_command(interaction: discord.Interaction, game_type: str):
    """Affiche la liste des jeux correspondant au type choisi."""
    try:
        query_type = game_type.lower().strip()
        cursor.execute("SELECT nom, type FROM games")
        games_found = cursor.fetchall()
        matching_games = []
        for nom, types in games_found:
            type_list = [t.strip().lower() for t in types.split(",")]
            if query_type in type_list:
                matching_games.append(nom.capitalize())
        if matching_games:
            embed = discord.Embed(
                title=f"Jeux du type {query_type.capitalize()}",
                color=discord.Color.blue()
            )
            embed.description = "\n".join(f"- {jeu}" for jeu in matching_games)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé pour le type '{query_type.capitalize()}'.", ephemeral=True)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des jeux pour le type : {str(e)}", ephemeral=True)

@type_command.autocomplete("game_type")
async def type_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = current.lower().strip()
    try:
        cursor.execute("SELECT DISTINCT type FROM games")
        types_found = cursor.fetchall()
        all_types = set()
        for row in types_found:
            for t in row[0].split(","):
                t_clean = t.strip()
                if t_clean:
                    all_types.add(t_clean.capitalize())
        suggestions = sorted([t for t in all_types if current_lower in t.lower()])
        return [app_commands.Choice(name=s, value=s) for s in suggestions]
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

@supprjeu.autocomplete("name")
async def supprjeu_autocomplete(interaction: discord.Interaction, current: str):
    """Propose les noms de jeux présents dans la bibliothèque pour le paramètre 'name'."""
    current_lower = current.strip().lower()
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
        results = cursor.fetchall()
        suggestions = [row[0] for row in results]
        return [app_commands.Choice(name=s.capitalize(), value=s) for s in suggestions]
    except Exception as e:
        conn.rollback()
        return []

bot.run(TOKEN)
