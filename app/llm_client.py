import requests
from app.config import GROQ_API_KEY

GROQ_MODEL = "openai/gpt-oss-20b"  # Example model

def call_groq(prompt: str, system_prompt: str = None):
    """
    Correct Groq API call using /openai/v1/responses.
    """
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # ✅ Groq expects plain string input, not chat messages
    full_prompt = f"{system_prompt or 'You are a finance analytics assistant.'}\nUser: {prompt}"

    payload = {
        "model": "openai/gpt-oss-20b",
        "input": full_prompt
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/responses",
        json=payload,
        headers=headers,
        timeout=15
    )

    if not response.ok:
        print("Groq error:", response.status_code, response.text)
        response.raise_for_status()

    data = response.json()
    return data.get("output_text", "")
