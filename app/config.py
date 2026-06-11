import os

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
PROJECT_PATH = os.getenv("PROJECT_PATH", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

