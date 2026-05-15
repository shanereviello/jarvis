import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEMORY_ROOT = os.getenv("JARVIS_MEMORY_ROOT", "memory")
VAULT_ROOT = os.getenv("JARVIS_VAULT_ROOT", "")
