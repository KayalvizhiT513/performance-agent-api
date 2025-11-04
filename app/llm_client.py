import requests
from app.config import GROQ_API_KEY
from groq import Groq

GROQ_MODEL = "openai/gpt-oss-20b"  

def call_groq(prompt: str, system_prompt: str = None) -> str:
    """
    Sends a structured prompt to Groq API and returns text response.
    """

    client = Groq(
        api_key=GROQ_API_KEY,
    )

    chat_completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages= [
            {"role": "system", "content": system_prompt or "You are a finance analytics assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    return chat_completion.choices[0].message.content
