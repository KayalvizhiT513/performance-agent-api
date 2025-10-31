import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATA_API_URL = os.getenv("DATA_API_URL")
FORMULA_API_URL = os.getenv("FORMULA_API_URL")
