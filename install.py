import os

# Mettre à jour les paquets et installer les dépendances
os.system('apt-get update')
os.system('apt-get install -y portaudio19-dev ffmpeg')

# Installer les dépendances Python
os.system('pip install discord.py gTTS vosk sounddevice')
