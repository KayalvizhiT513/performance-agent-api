from fastapi import APIRouter
from app.models import QueryRequest
from app.orchestrator import orchestrate_query, ConversationState

router = APIRouter()

# 🧠 In-memory conversation store
sessions = {}

@router.post("/query")
def process_query(request: QueryRequest):
    # Use session_id from client if available, else default
    session_id = getattr(request, "session_id", "default")

    # ✅ Reuse or create conversation state
    if session_id not in sessions:
        sessions[session_id] = ConversationState()

    state = sessions[session_id]

    # Preserve history from frontend if provided (optional)
    if request.history:
        state.history = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # 🔥 Process user query
    result = orchestrate_query(request.query, state)

    # 🧩 Detect completion (simple heuristics)
    is_completed = result.strip().startswith("✅") or "result" in result.lower()

    # 🧹 If done, clear session to start fresh next time
    if is_completed:
        sessions.pop(session_id, None)

    return {
        "response": result,
        "history": state.history,
        "params": state.params,
        "current_endpoint": (
            state.current_endpoint.get("name")
            if state.current_endpoint else None
        ),
        "session_cleared": is_completed
    }
