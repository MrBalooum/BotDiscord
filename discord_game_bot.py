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

@bot.tree.command(name="fiche", description="Affiche la fiche détaillée d'un jeu")
async def fiche(interaction: discord.Interaction, game: str):
    """Affiche la fiche d'un jeu dont le nom est fourni."""
    game_query = game.strip().lower()
    try:
        cursor.execute("""
            SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link
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
            await interaction.response.send_message(embed=embed)
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

@bot.tree.command(name="demandes", description="Affiche la liste des demandes (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def demandes(interaction: discord.Interaction):
    """Affiche la liste des demandes d'ajout de jeu."""
    try:
        cursor.execute("SELECT username, game_name, date FROM game_requests ORDER BY date DESC")
        requests_data = cursor.fetchall()
        if requests_data:
            request_list = "\n".join(
                f"- **{r[1]}** (demandé par {r[0]} le {r[2].strftime('%d/%m')})" for r in requests_data
            )
            await interaction.response.send_message(f"📜 **Liste des jeux demandés :**\n```{request_list}```")
        else:
            await interaction.response.send_message("📭 **Aucune demande en attente.**")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur SQL: {str(e)}", ephemeral=True)

@bot.tree.command(name="supprdemande", description="Supprime une demande (ADMIN)")
@commands.has_permissions(administrator=True)
async def supprdemande(interaction: discord.Interaction, game_name: str):
    """Supprime une demande d'ajout de jeu."""
    try:
        cursor.execute("SELECT * FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
        demande = cursor.fetchone()
        if demande:
            cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (game_name.lower(),))
            conn.commit()
            await interaction.response.send_message(f"🗑️ La demande pour **{game_name.capitalize()}** a été supprimée.")
        else:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé dans la liste des demandes sous le nom '{game_name}'.")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la suppression de la demande : {str(e)}", ephemeral=True)

@bot.tree.command(name="modifjeu", description="Modifie un champ d'un jeu (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def modifjeu(interaction: discord.Interaction, name: str, champ: str, nouvelle_valeur: str):
    """
    Modifie une propriété d'un jeu existant.
    
    Format d'utilisation :
    /modifjeu "Nom du jeu" "Champ" "Nouvelle valeur"
    
    Exemple :
    /modifjeu "Halo Infinite" "prix" "39.99 €"
    """
    try:
        name_clean = name.strip().lower()
        cursor.execute("""
            SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link 
            FROM games 
            WHERE LOWER(nom) LIKE %s
        """, (f"%{name_clean}%",))
        jeu = cursor.fetchone()
        if not jeu:
            await interaction.response.send_message(f"❌ Aucun jeu trouvé avec le nom '{name.capitalize()}'.", ephemeral=True)
            return

        mapping = {
            "nom": "nom",
            "name": "nom",
            "sortie": "release_date",
            "prix": "price",
            "type": "type",
            "durée": "duration",
            "duree": "duration",
            "cloud": "cloud_available",
            "youtube": "youtube_link",
            "steam": "steam_link"
        }
        champ_clean = champ.strip().lower()
        if champ_clean not in mapping:
            await interaction.response.send_message(
                f"❌ Le champ '{champ}' n'est pas valide. Champs autorisés : {', '.join(mapping.keys())}",
                ephemeral=True
            )
            return
        actual_field = mapping[champ_clean]
        query = f'UPDATE games SET {actual_field} = %s WHERE LOWER(nom) LIKE %s'
        cursor.execute(query, (nouvelle_valeur, f"%{name_clean}%"))
        conn.commit()
        await interaction.response.send_message(f"✅ Jeu '{jeu[0].capitalize()}' mis à jour : {champ_clean} → {nouvelle_valeur}")
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la modification du jeu : {str(e)}", ephemeral=True)

@modifjeu.autocomplete("name")
async def modifjeu_autocomplete(interaction: discord.Interaction, current: str):
    """Propose des noms de jeux présents dans la bibliothèque pour le paramètre 'name'."""
    current_lower = current.lower().strip()
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) LIKE %s ORDER BY nom ASC LIMIT 25", (f"%{current_lower}%",))
        results = cursor.fetchall()
        suggestions = [row[0].capitalize() for row in results]
        return [app_commands.Choice(name=s, value=s) for s in suggestions]
    except Exception as e:
        conn.rollback()
        return []

@bot.tree.command(name="ajoutjeu", description="Ajoute un jeu (ADMIN)")
@commands.has_permissions(administrator=True)
async def ajoutjeu(interaction: discord.Interaction, name: str, release_date: str, price: str, types: str, duration: str, cloud_available: str, youtube_link: str, steam_link: str):
    """Ajoute un nouveau jeu et envoie la fiche dans le salon 'général'."""
    try:
        cursor.execute(
            "INSERT INTO games (nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
            (name.lower(), release_date, price, types.lower(), duration, cloud_available, youtube_link, steam_link)
        )
        save_database()
        cursor.execute("DELETE FROM game_requests WHERE LOWER(game_name) = %s", (name.lower(),))
        conn.commit()
        cursor.execute("""
            SELECT nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link 
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

@bot.tree.command(name="ajoutjeux", description="Ajoute plusieurs jeux à la fois (ADMIN)")
@app_commands.check(lambda interaction: interaction.user.guild_permissions.administrator)
async def ajoutjeux(interaction: discord.Interaction, games: str):
    """
    Ajoute plusieurs jeux à partir d'un bloc de texte.
    Chaque jeu doit être défini par exactement 8 valeurs entre guillemets :
    "Nom du jeu" "Date de sortie" "Prix" "Type" "Durée" "Cloud" "Lien yt" "Lien steam"
    Vous pouvez séparer les jeux par des retours à la ligne, des espaces ou des séparateurs.
    """
    import re
    pattern = r'"(.*?)"'
    # Extrait toutes les valeurs entre guillemets dans le bloc
    matches = re.findall(pattern, games)
    total = len(matches)
    if total % 8 != 0:
        await interaction.response.send_message(
            f"❌ Erreur : le nombre total de valeurs extraites est {total}, "
            "ce qui n'est pas un multiple de 8. Veuillez vérifier le format de votre texte.",
            ephemeral=True
        )
        return

    added_games = []
    errors = []
    # Traiter chaque groupe de 8 valeurs comme un jeu
    for i in range(0, total, 8):
        nom, date_sortie, prix, type_jeu, duree, cloud, lien_yt, lien_steam = matches[i:i+8]
        try:
            cursor.execute(
                "INSERT INTO games (nom, release_date, price, type, duration, cloud_available, youtube_link, steam_link) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (nom.lower(), date_sortie, prix, type_jeu.lower(), duree, cloud, lien_yt, lien_steam)
            )
            added_games.append(nom)
        except Exception as e:
            conn.rollback()
            errors.append(f"Erreur pour '{nom}': {str(e)}")
    try:
        conn.commit()
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la sauvegarde: {str(e)}", ephemeral=True)
        return

    response = ""
    if added_games:
        response += f"✅ Jeux ajoutés : {', '.join(added_games)}\n"
    if errors:
        response += "❌ Erreurs :\n" + "\n".join(errors)
    
    await interaction.response.send_message(response)

@bot.tree.command(name="supprjeu", description="Supprime un jeu (ADMIN)")
@commands.has_permissions(administrator=True)
async def supprjeu_slash(interaction: discord.Interaction, name: str):
    """Supprime un jeu de la base et envoie une notification dans 'général'."""
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) = %s", (name.lower(),))
        jeu = cursor.fetchone()
        if jeu:
            cursor.execute("DELETE FROM games WHERE LOWER(nom) = %s", (name.lower(),))
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

@bot.tree.command(name="listejeux", description="Affiche les jeux enregistrés (15 par page)")
async def listejeux(interaction: discord.Interaction):
    """Affiche la liste des jeux enregistrés, paginée 15 par page."""
    try:
        cursor.execute("SELECT nom FROM games ORDER BY LOWER(nom) ASC")
        games = cursor.fetchall()
        if not games:
            await interaction.response.send_message("❌ Aucun jeu enregistré.")
            return
        game_names = [game[0].capitalize() for game in games]
        pages = [game_names[i:i+15] for i in range(0, len(game_names), 15)]
        embeds = []
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"🎮 Liste des jeux enregistrés (Page {idx}/{len(pages)})",
                color=discord.Color.blue()
            )
            embed.description = "\n".join(f"- {name}" for name in page)
            embeds.append(embed)
        if len(embeds) == 1:
            await interaction.response.send_message(embed=embeds[0])
        else:
            view = PaginationView(embeds)
            await interaction.response.send_message(embed=embeds[0], view=view)
    except Exception as e:
        conn.rollback()
        await interaction.response.send_message(f"❌ Erreur lors de la récupération des jeux : {str(e)}", ephemeral=True)

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

############################################
#         COMMANDES CLASSIQUES
############################################

@bot.command(aliases=["Supprjeu"])
@commands.has_permissions(administrator=True)
async def supprjeu(ctx, name: str):
    """Supprime un jeu de la base et notifie dans le salon 'général'."""
    try:
        cursor.execute("SELECT nom FROM games WHERE LOWER(nom) = %s", (name.lower(),))
        jeu = cursor.fetchone()
        if jeu:
            cursor.execute("DELETE FROM games WHERE LOWER(nom) = %s", (name.lower(),))
            save_database()
            await ctx.send(f"🗑️ Jeu '{name.capitalize()}' supprimé avec succès !")
            general_channel = discord.utils.get(ctx.guild.text_channels, name="général")
            if general_channel:
                await general_channel.send(f"📣 **{name.capitalize()}** n'est plus disponible !")
        else:
            await ctx.send(f"❌ Aucun jeu trouvé avec le nom '{name}'.")
    except Exception as e:
        conn.rollback()
        await ctx.send(f"❌ Erreur lors de la suppression du jeu : {str(e)}")

bot.run(TOKEN)
