import requests
from app.config import OPENAI_API_KEY
from openai import OpenAI

OPENAI_MODEL = "gpt-4o"

def call_groq(prompt: str, system_prompt: str = None) -> str:
    """
    Sends a structured prompt to OpenAI API and returns text response.
    """

    client = OpenAI(
        api_key=OPENAI_API_KEY,
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    chat_completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages
    )
    return chat_completion.choices[0].message.content
