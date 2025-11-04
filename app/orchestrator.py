import json
import re
from typing import Any, Dict

import requests
from app.config import FORMULA_API_URL
from app.llm_client import call_groq
from app.nl_query_runner import run_nl_query

def safe_parse_llm_output(parsed):
    if not isinstance(parsed, str):
        return parsed

    # Step 1: Remove ```json or ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", parsed.strip())

    # Step 2: Parse JSON safely
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "Could not parse LLM response.", "raw": parsed}

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
    print("LLM Parsed Output:", parsed)

    try:
        intent_data = safe_parse_llm_output(parsed)
        print("Parsed Intent Data:", intent_data)
    except Exception:
        return {"error": "Could not parse LLM response.", "raw": parsed}

    intent = intent_data.get("intent")

    # 2️⃣ Route based on intent
    if intent == "get_data":
        return handle_get_data(intent_data, user_query)

    elif intent == "compute_metric":
        return handle_compute_metric(intent_data, user_query)

    elif intent == "clarify":
        return {"message": "Please clarify your request.", "suggestions": ["Specify fund name or metric."]}

    else:
        return {"error": "Unrecognized intent", "details": intent_data}


def handle_get_data(intent_data, user_query: str):
    """
    Call Data API to retrieve portfolio returns
    """
    try:
        nl_result = run_nl_query(user_query)
        sql_text = nl_result["sql"]
        params = nl_result.get("params")
        rows = nl_result.get("rows", [])
        return {
            "intent": "get_data",
            "sql": sql_text,
            "params": params,
            "row_count": len(rows),
            "preview": rows[:5],
        }

    except Exception as e:
        return {"error": str(e)}


def handle_compute_metric(intent_data, user_query: str):
    """
    Calls both Data API and Formula API to produce a computed result
    """
    try:
        metric = intent_data.get("metric")
        nl_result = run_nl_query(user_query)
        sql_text = nl_result["sql"]
        rows = nl_result.get("rows", [])

        return_column = "return_value"
        if rows and isinstance(rows[0], dict) and return_column not in rows[0]:
            fallback = next((key for key in rows[0].keys() if "return" in key.lower()), None)
            if fallback:
                return_column = fallback

        daily_returns = [
            row[return_column]
            for row in rows
            if isinstance(row, dict) and return_column in row and row[return_column] is not None
        ]

        formula_payload = {"metric": metric, "inputs": {"returns": daily_returns}}
        formula_response = requests.post(f"{FORMULA_API_URL}/compute", json=formula_payload)
        if formula_response.status_code >= 400:
            raise RuntimeError(f"Formula API error: {formula_response.status_code} {formula_response.text}")

        result = formula_response.json()

        return {
            "intent": "compute_metric",
            "metric": metric,
            "sql": sql_text,
            "row_count": len(rows),
            "value": result.get("value"),
            "methodology": result.get("methodology", ""),
            "preview": rows[:5],
            "return_column": return_column,
        }

    except Exception as e:
        return {"error": str(e)}
