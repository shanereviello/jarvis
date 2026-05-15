import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JARVIS_MEMORY_ROOT = os.getenv("JARVIS_MEMORY_ROOT", "memory")
JARVIS_VAULT_ROOT = os.getenv("JARVIS_VAULT_ROOT", "")
