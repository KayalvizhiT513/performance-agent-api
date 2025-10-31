import requests
from app.config import GROQ_API_KEY

GROQ_MODEL = "openai/gpt-oss-20b"  # Example model

def call_groq(prompt: str, system_prompt: str = None) -> str:
    """
    Sends a structured prompt to Groq API and returns text response.
    """
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a financial analytics assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    response = requests.post("https://api.groq.com/openai/v1/responses", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
