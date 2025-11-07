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
import os
from typing import Any, Dict, Optional
import requests
from app.llm_client import call_groq
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from urllib.parse import urljoin
import time
from app.rag_helper import rag_index
from app.rag_helper import initialize_rag_from_docs
from pymongo import MongoClient
from app.config import MONGO_URL

# Global storage for API specs
global_apis_info = []
global_validation_rules = {}
specs_ready = False

def get_mongo_collection():
    try:
        client = MongoClient(MONGO_URL)
        db = client["finperf"]
        return db["api_specs"]
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        return None

def load_specs_from_mongo():
    collection = get_mongo_collection()
    if collection is not None:
        doc = collection.find_one({"type": "specs"})
        if doc:
            return doc.get("apis", []), doc.get("validation_rules", {})
    return [], {}

# ==============================
# State and Configuration
# ==============================

class ConversationState:
    def __init__(self):
        # Load latest specs from MongoDB
        apis, rules = load_specs_from_mongo()
        self.api_specs = {"apis": apis, "validation_rules": rules}
        self.current_endpoint: Optional[Dict[str, Any]] = None
        self.params: Dict[str, Any] = {}
        self.history = []


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
    Validates parameters using the endpoint's validation_rules.
    Returns dict of {param_name: reason} for invalid ones.
    """
    validation_rules = endpoint.get("validation_rules", {})
    if not validation_rules:
        return {}

    rules_text = "\n".join([f"- {p}: {r}" for p, r in validation_rules.items()])
    params_text = json.dumps(params, indent=2)

    prompt = f"""
    You are a strict API validation agent.
    Check each parameter's value against its validation rule.

    === RULES ===
    {rules_text}

    === PARAMETERS ===
    {params_text}

    If any rule is violated, describe why.

    Respond in valid JSON:
    {{
      "validation_errors": {{
        "param_name": "reason for violation",
        ...
      }}
    }}
    """

    try:
        llm_output = call_groq("", prompt).strip()
        llm_output = re.sub(r"^```(?:json)?|```$", "", llm_output).strip()
        parsed = json.loads(llm_output)

        if not isinstance(parsed, dict):
            return {}

        errors = parsed.get("validation_errors", {})
        if isinstance(errors, dict):
            return errors
        return {}

    except Exception as e:
        print(f"⚠️ LLM validation failed: {e}")
        return {}
        
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

def check_name_in_db(name: str, name_type: str) -> Dict[str, Any]:
    """
    Load all names from MongoDB, give to LLM to find match.
    Returns {"exists": bool, "matched": str or None, "closest": [list]}
    """
    try:
        # Load names from MongoDB
        collection = get_mongo_collection()
        if collection is not None:
            doc = collection.find_one({"type": "specs"})
            if doc:
                if name_type == "portfolio":
                    all_names = doc.get("portfolio_names", [])
                elif name_type == "benchmark":
                    all_names = doc.get("benchmark_names", [])
                else:
                    all_names = []
            else:
                all_names = []
        else:
            return {"error": "MongoDB connection failed"}

        if not all_names:
            return {"exists": False, "matched": None, "closest": []}

        # Use LLM to find match
        match_prompt = f"""
        User provided name: "{name}"
        Available {name_type} names: {', '.join(all_names)}

        Determine:
        - Exact match: If there's an exact match (case-insensitive), return it.
        - Closest matches: Up to 3 closest similar names.
        - If no match, return empty.

        Output JSON:
        {{
          "matched": "exact_name" or null,
          "closest": ["name1", "name2", "name3"] or []
        }}
        """
        llm_response = call_groq("", match_prompt)
        parsed = json.loads(llm_response) if isinstance(llm_response, str) else llm_response

        matched = parsed.get("matched")
        closest = parsed.get("closest", [])

        if matched:
            return {"exists": True, "matched": matched, "closest": []}
        else:
            return {"exists": False, "matched": None, "closest": closest}

    except Exception as e:
        return {"error": str(e)}

def call_api(endpoint: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the API call based on endpoint definition.
    """
    base_url = endpoint.get("base_url", "https://performance-analytics-api.onrender.com")
    route = endpoint.get("route")
    method = endpoint.get("method", "GET").upper()

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

def merge_user_fix_into_state(user_input, state, endpoint):
    expected_params = {p["name"] for p in endpoint.get("parameters", [])}
    matches = re.findall(r"(\w+)\s*=\s*([\w\-]+)", user_input)
    if matches:
        for k, v in matches:
            if k in expected_params:
                state.params[k] = v
    else:
        # handle natural language, e.g. “start date is ...”
        correction_prompt = f"""
        Extract parameter name and value from: "{user_input}"
        Known parameters: {', '.join(expected_params)}
        Output JSON: {{"param": "name", "value": "..."}} or null.
        """
        extraction = call_groq("", correction_prompt)
        try:
            parsed = json.loads(extraction)
            if parsed and isinstance(parsed, dict) and parsed.get("param") in expected_params:
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
    state.history.append({"role": "user", "content": user_query})

    # Specs should be built on page refresh, not per query

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

    # Merge user corrections (only for known params)
    merge_user_fix_into_state(user_query, state, endpoint)

    # Filter to only include params defined in the endpoint schema
    expected_params = {p["name"] for p in endpoint.get("parameters", [])}
    state.params = {k: v for k, v in state.params.items() if k in expected_params}

    # Validate parameters
    validation_errors = validate_parameters_with_llm(state.params, endpoint)
    if validation_errors:
        error_lines = "\n".join(f"• {k}: {v}" for k, v in validation_errors.items())
        msg = f"Some parameters are invalid:\n{error_lines}\nPlease correct them."
        state.history.append({"role": "assistant", "content": msg})
        return msg

    # Check name existence in database (portfolio or benchmark)
    for param_name in ["portfolio_name", "benchmark_name"]:
        if param_name in state.params:
            name_type = param_name.split("_")[0] + "s"  # portfolio or benchmark
            name_check = check_name_in_db(state.params[param_name], name_type)
            if name_check.get("error"):
                msg = f"❌ Error checking {name_type}: {name_check['error']}"
                state.history.append({"role": "assistant", "content": msg})
                return msg
            elif name_check.get("exists"):
                # Update to matched name if different
                matched = name_check.get("matched")
                if matched and matched != state.params[param_name]:
                    state.params[param_name] = matched
            else:
                closest = name_check.get("closest", [])
                display_name = name_type.capitalize()
                if closest:
                    suggestion_text = "\n".join(f"• {s}" for s in closest)
                    msg = f"{display_name} '{state.params[param_name]}' not found. Closest matches:\n{suggestion_text}\nPlease confirm or provide the correct name."
                else:
                    msg = f"{display_name} '{state.params[param_name]}' not found in database."
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
