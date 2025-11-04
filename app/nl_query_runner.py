from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict

import requests

from app.config import DATA_API_URL
from app.llm_client import call_groq


class _RequestsAPIClient:
    def __init__(self, base_url: str) -> None:
        if not base_url:
            raise RuntimeError("DATA_API_URL is not configured")
        self._base_url = base_url.rstrip("/")

    def get(self, path: str):
        return requests.get(self._base_url + path)

    def post(self, path: str, json: Dict[str, Any]):
        return requests.post(self._base_url + path, json=json)


class _GroqLLMClient:
    _SYSTEM_PROMPT = (
        "You are an assistant that only returns JSON containing SQL queries. "
        "Follow instructions precisely."
    )

    def complete(self, prompt: str) -> str:
        return call_groq(prompt, system_prompt=self._SYSTEM_PROMPT)


def _load_nl_module():
    module_path = Path(__file__).resolve().parents[2] / "data_api" / "app" / "services" / "nl_query_executor.py"
    if not module_path.exists():
        raise RuntimeError(f"Could not locate NL query executor module at {module_path}")

    spec = importlib.util.spec_from_file_location("data_api.nl_query_executor", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to prepare import spec for NL query executor")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


_module = _load_nl_module()
NLQueryExecutor = _module.NLQueryExecutor

_executor = None


def _get_executor():
    global _executor
    if _executor is None:
        api_client = _RequestsAPIClient(DATA_API_URL)
        llm_client = _GroqLLMClient()
        _executor = NLQueryExecutor(api_client, llm_client)
    return _executor


def run_nl_query(user_input: str) -> Dict[str, Any]:
    executor = _get_executor()
    return executor.run(user_input)
