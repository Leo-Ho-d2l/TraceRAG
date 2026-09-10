from fastapi import APIRouter

from app.api.deps import Auth, DBSession
from app.retrieval.hybrid import HybridRetriever
from app.schemas.search import SearchHitOut, SearchRequest, SearchResponse

router = APIRouter(prefix="/v1/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_corpus(request: SearchRequest, session: DBSession, _auth: Auth) -> SearchResponse:
    hits, cached = await HybridRetriever(session).retrieve(
        request.query,
        top_k=request.top_k,
        document_ids=request.document_ids,
        rerank=request.rerank,
        strategy=request.strategy,
    )
    return SearchResponse(
        query=request.query,
        cached=cached,
        hits=[
            SearchHitOut(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                filename=hit.filename,
                section_title=hit.section_title,
                page_number=hit.page_number,
                content=hit.content,
                score=hit.score,
                dense_score=hit.dense_score,
                sparse_score=hit.sparse_score,
                rrf_score=hit.rrf_score,
                rerank_score=hit.rerank_score,
                metadata=hit.metadata,
            )
            for hit in hits
        ],
    )
