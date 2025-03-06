import subprocess
import sys

# Installer les dépendances Python
subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py", "gTTS", "vosk", "sounddevice"])
