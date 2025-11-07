"""
Simplified deterministic orchestrator for FinPerf conversational API interface.

Responsibilities:
- Parse user query
- Identify matching endpoint
- Extract parameters (via minimal LLM use)
- Ask user for missing or invalid parameters
- Call the correct API and return results

Dependencies:
- llm_client.call_groq (for controlled extraction)
- Structured JSON doc of APIs (auto-generated offline)
"""

import json
import re
from typing import Any, Dict, Optional
import requests
from app.llm_client import call_groq

# ==============================
# State and Configuration
# ==============================

class ConversationState:
    def __init__(self, api_specs_path: str = "app/finperf_api_specs.json"):
        self.api_specs = self._load_api_specs(api_specs_path)
        self.current_endpoint: Optional[Dict[str, Any]] = None
        self.params: Dict[str, Any] = {}
        self.history = []

    def _load_api_specs(self, path: str) -> Dict[str, Any]:
        with open(path, "r") as f:
            return json.load(f)


# ==============================
# Core Matching and Extraction
# ==============================

def match_endpoint(user_query: str, api_specs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Deterministically match the user query to the right API endpoint
    based on known names, routes, and keywords.
    """
    query = user_query.lower()

    for api in api_specs.get("apis", []):
        name = api.get("name", "").lower().replace("_", " ")
        route = api.get("route", "").lower()
        keywords = [k.lower() for k in api.get("keywords", [])]

        # Direct name or route match
        if name in query or route in query:
            return api

        # Keyword match
        if any(kw in query for kw in keywords):
            return api

    return None


def extract_parameters_with_llm(user_query: str, endpoint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use LLM to extract parameter values from user query based on endpoint schema.
    Deterministic prompt (temperature=0 equivalent).
    """
    params = endpoint.get("parameters", [])
    if not params:
        return {}

    param_names = [p["name"] for p in params]
    prompt = f"""
    You are an information extraction model.

    Extract the following parameters from the user's request.
    If not mentioned, set value to null.

    Required parameters: {', '.join(param_names)}

    User query: "{user_query}"

    Respond with valid JSON only:
    {{
      {', '.join([f'"{p}": "value or null"' for p in param_names])}
    }}
    """

    llm_output = call_groq("", prompt)
    try:
        parsed = json.loads(re.sub(r"^```(?:json)?|```$", "", llm_output.strip()))
        return {k: v for k, v in parsed.items() if v and v.lower() != "null"}
    except Exception:
        return {}


from app.llm_client import call_groq
import json

def validate_parameters_with_llm(params: dict, endpoint: dict) -> dict:
    """
    Validates parameters using LLM + endpoint validation_rules.
    Returns dict of {param_name: error_message} for invalid ones.
    """
    validation_rules = endpoint.get("validation_rules", {})
    if not validation_rules:
        return {}

    results = {}

    for param, rule in validation_rules.items():
        if param not in params:
            continue  # skip missing ones; handled by missing check

        value = params[param]

        validation_prompt = f"""
        You are a validation agent. Check if the following parameter value obeys its rule.
        You don't to check if there are in database, just the format/content.

        Parameter name: {param}
        Value: {value}
        Rule: {rule}

        If it violates the rule, explain briefly why.
        Otherwise say "valid".

        Respond ONLY in valid JSON:
        {{
          "param": "{param}",
          "valid": true or false,
          "reason": "why invalid if applicable"
        }}
        """

        try:
            result = call_groq("", validation_prompt)
            result = result.strip().replace("```json", "").replace("```", "")
            parsed = json.loads(result)

            if not parsed.get("valid", True):
                results[param] = parsed.get("reason", "Invalid value.")
        except Exception as e:
            results[param] = f"Validation failed: {e}"

    return results

def _is_before(date1: str, date2: str) -> bool:
    from datetime import datetime
    try:
        d1 = datetime.fromisoformat(date1)
        d2 = datetime.fromisoformat(date2)
        return d1 < d2
    except Exception:
        return True  # don't block if format can't be parsed


def find_missing_params(params: Dict[str, Any], endpoint: Dict[str, Any]) -> list:
    required = [p["name"] for p in endpoint.get("parameters", []) if p.get("required")]
    return [r for r in required if r not in params]


# ==============================
# API Execution
# ==============================

def call_api(endpoint: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the API call based on endpoint definition.
    """
    base_url = endpoint.get("base_url", "http://localhost:8002")
    route = endpoint.get("route")
    method = endpoint.get("method", "POST").upper()

    url = f"{base_url}{route}"

    try:
        if method == "GET":
            resp = requests.get(url, params=params)
        else:
            resp = requests.post(url, json=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def merge_user_fix_into_state(user_input, state):
    matches = re.findall(r"(\w+)\s*=\s*([\w\-]+)", user_input)
    if matches:
        for k, v in matches:
            state.params[k] = v
    else:
        # handle natural language, e.g. “start date is ...”
        correction_prompt = f"""
        Extract parameter name and value from: "{user_input}"
        Output JSON: {{"param": "name", "value": "..."}} or null.
        """
        extraction = call_groq("", correction_prompt)
        try:
            parsed = json.loads(extraction)
            if parsed and isinstance(parsed, dict):
                state.params[parsed["param"]] = parsed["value"]
        except Exception:
            pass

# ==============================
# Main Orchestration Logic
# ==============================

def orchestrate_query(user_query: str, state: ConversationState):
    """
    Main orchestration loop:
    - Identify endpoint
    - Extract and validate parameters
    - Handle missing or invalid ones
    - Call the API
    """
    print(f"State before query: {state.params}")
    merge_user_fix_into_state(user_query, state)
    state.history.append({"role": "user", "content": user_query})

    # Identify API endpoint
    endpoint = match_endpoint(user_query, state.api_specs)
    if not endpoint and state.current_endpoint:
        endpoint = state.current_endpoint

    if not endpoint:
        msg = "❓ I couldn't identify which API to call. Please rephrase your request."
        state.history.append({"role": "assistant", "content": msg})
        return msg

    state.current_endpoint = endpoint

    # Extract parameters
    extracted = extract_parameters_with_llm(user_query, endpoint)
    state.params.update(extracted)

    # Validate parameters
    validation_errors = validate_parameters_with_llm(state.params, endpoint)
    if validation_errors:
        error_lines = "\n".join(f"• {k}: {v}" for k, v in validation_errors.items())
        msg = f"Some parameters are invalid:\n{error_lines}\nPlease correct them."
        state.history.append({"role": "assistant", "content": msg})
        return msg

    # Check for missing parameters
    missing = find_missing_params(state.params, endpoint)
    if missing:
        msg = f"I still need the following parameters: {', '.join(missing)}."
        state.history.append({"role": "assistant", "content": msg})
        return msg

    # All good → call API
    result = call_api(endpoint, state.params)

    if "error" in result:
        msg = f"❌ API call failed: {result['error']}"
    else:
        msg = f"✅ {endpoint['name']} result:\n{json.dumps(result, indent=2)}"

    state.history.append({"role": "assistant", "content": msg})
    return msg
