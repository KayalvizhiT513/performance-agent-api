from fastapi import FastAPI
from app.routes import router

app = FastAPI(
    title="Agent API - Performance Analytics",
    version="1.0.0",
    description="Groq LLM-powered orchestration API for investment performance analytics."
)

app.include_router(router)
