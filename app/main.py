from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.routes import router
import os

app = FastAPI(
    title="Agent API - Performance Analytics",
    version="1.0.0",
    description="OpenAI LLM-powered orchestration API for investment performance analytics."
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html at root
@app.get("/")
async def read_index():
    index_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    return FileResponse(index_path)

app.include_router(router)
