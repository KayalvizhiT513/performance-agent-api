import requests
from app.config import DATA_API_URL, FORMULA_API_URL
from app.llm_client import call_groq

def orchestrate_query(user_query: str):
    """
    Main orchestration logic:
    - Parse user intent
    - Fetch data or compute metrics
    - Handle clarifications
    """

    # 1️⃣ Ask LLM to parse the intent
    system_prompt = """You are an investment analytics agent.
    Parse the user's query and output a JSON object like:
    {
      "intent": "get_data" | "compute_metric" | "clarify",
      "portfolio_name": "<optional>",
      "benchmark_name": "<optional>",
      "metric": "<optional>",
      "period": "<e.g. 5Y, 1Y>"
    }"""

    parsed = call_groq(user_query, system_prompt)

    try:
        intent_data = eval(parsed) if isinstance(parsed, str) else parsed
    except Exception:
        return {"error": "Could not parse LLM response.", "raw": parsed}

    intent = intent_data.get("intent")

    # 2️⃣ Route based on intent
    if intent == "get_data":
        return handle_get_data(intent_data)

    elif intent == "compute_metric":
        return handle_compute_metric(intent_data)

    elif intent == "clarify":
        return {"message": "Please clarify your request.", "suggestions": ["Specify fund name or metric."]}

    else:
        return {"error": "Unrecognized intent", "details": intent_data}


def handle_get_data(intent_data):
    """
    Call Data API to retrieve portfolio returns
    """
    try:
        portfolio_name = intent_data.get("portfolio_name")
        res = requests.get(f"{DATA_API_URL}/portfolios").json()
        match = next((p for p in res if p["portfolio_name"].lower() == portfolio_name.lower()), None)

        if not match:
            return {"clarification": f"No portfolio found with name '{portfolio_name}'."}

        portfolio_id = match["id"]
        returns_data = requests.get(f"{DATA_API_URL}/returns/{portfolio_id}").json()

        return {
            "intent": "get_data",
            "portfolio": portfolio_name,
            "data_points": len(returns_data),
            "preview": returns_data[:5]
        }

    except Exception as e:
        return {"error": str(e)}


def handle_compute_metric(intent_data):
    """
    Calls both Data API and Formula API to produce a computed result
    """
    try:
        portfolio_name = intent_data.get("portfolio_name")
        metric = intent_data.get("metric")
        period = intent_data.get("period", "5Y")

        # Get portfolio info
        portfolios = requests.get(f"{DATA_API_URL}/portfolios").json()
        portfolio = next((p for p in portfolios if p["portfolio_name"].lower() == portfolio_name.lower()), None)
        if not portfolio:
            return {"clarification": f"Portfolio '{portfolio_name}' not found."}

        portfolio_id = portfolio["id"]
        returns_data = requests.get(f"{DATA_API_URL}/returns/{portfolio_id}").json()
        daily_returns = [r["portfolio_return"] for r in returns_data if r["portfolio_return"] is not None]

        # Compute metric
        formula_payload = {"metric": metric, "inputs": {"returns": daily_returns}}
        result = requests.post(f"{FORMULA_API_URL}/compute", json=formula_payload).json()

        return {
            "intent": "compute_metric",
            "metric": metric,
            "portfolio": portfolio_name,
            "value": result.get("value"),
            "methodology": result.get("methodology", ""),
        }

    except Exception as e:
        return {"error": str(e)}
