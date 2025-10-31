import os
from groq import Groq

# Initialize the Groq client once
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def call_groq(prompt: str, system_prompt: str = None) -> str:
    """
    Calls Groq LLM (chat.completions) and returns the model output.
    """
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages
    )

    return response.choices[0].message.content
