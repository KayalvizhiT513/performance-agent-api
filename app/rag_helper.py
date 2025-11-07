# rag_helper.py
import faiss
import numpy as np
from openai import OpenAI
import json

from app.config import OPENAI_API_KEY

EMBED_MODEL = "text-embedding-3-small"

client = OpenAI(api_key=OPENAI_API_KEY)

class RAGIndex:
    def __init__(self):
        self.docs = []
        self.index = None
        self.embeddings = None

    def build(self, api_docs):
        """
        api_docs: list[str] — all documentation chunks (from Selenium scraping)
        """
        print(f"🔧 Building RAG index with {len(api_docs)} docs...")
        self.docs = api_docs
        embeddings = client.embeddings.create(model=EMBED_MODEL, input=api_docs)
        self.embeddings = np.array([e.embedding for e in embeddings.data], dtype=np.float32)
        self.index = faiss.IndexFlatL2(self.embeddings.shape[1])
        self.index.add(self.embeddings)
        print("✅ RAG index ready.")

    def retrieve(self, query, k=3):
        """
        Retrieve top-k most relevant documentation chunks for a given query.
        """
        q_emb = client.embeddings.create(model=EMBED_MODEL, input=[query])
        q_vec = np.array(q_emb.data[0].embedding, dtype=np.float32).reshape(1, -1)
        distances, indices = self.index.search(q_vec, k)
        results = [self.docs[i] for i in indices[0]]
        return results


# Global shared RAG index (initialized once)
rag_index = RAGIndex()

def initialize_rag_from_docs(route_text_map):
    """
    Called after fetch_api_documentation() — flatten route_text_map into list of docs.
    """
    merged_docs = []
    for route, text in route_text_map.items():
        merged_docs.append(f"[Route: {route}]\n{text}")
    rag_index.build(merged_docs)
    return rag_index
