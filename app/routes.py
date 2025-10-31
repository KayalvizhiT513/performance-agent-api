from fastapi import APIRouter
from app.orchestrator import orchestrate_query

router = APIRouter()

@router.post("/query")
def process_query(payload: dict):
    user_query = payload.get("query", "")
    if not user_query:
        return {"error": "Missing 'query' in request body."}

    result = orchestrate_query(user_query)
    return result
