"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from database.db import init_db
from knowledge.graph_store import graph_loaded
from api.routes import router

app = FastAPI(
    title="Adaalat AI",
    description="Pakistan's AI Legal Agent — Alpha Mates",
    version="2.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app.include_router(router, prefix="/api/v1")

# Ensure static directory exists
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")


@app.on_event("startup")
async def startup():
    logger.info("Starting Adaalat AI v2 (OpenAI + Marker pipeline)...")
    init_db()
    if graph_loaded():
        from knowledge.graph_store import get_graph
        g = get_graph()
        logger.success(
            f"Legal knowledge base ready: "
            f"{g.number_of_nodes()} nodes, {g.number_of_edges()} edges"
        )
    else:
        logger.warning(
            "Legal knowledge base NOT loaded. "
            "Run scripts/run_marker.sh then scripts/build_index.py."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
