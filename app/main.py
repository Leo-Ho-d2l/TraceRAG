from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.observability.tracing import configure_tracing

configure_logging()
configure_tracing()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="TraceRAG",
    version="0.1.0",
    description="Agentic RAG with hybrid retrieval, reranking, tool use, evaluation and tracing.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)
app.include_router(api_router)
FastAPIInstrumentor.instrument_app(app)


@app.get("/", include_in_schema=False)
async def demo_ui():
    return FileResponse("app/web/index.html")
