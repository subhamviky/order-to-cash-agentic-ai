from fastapi import APIRouter, Depends, HTTPException, WorkflowRequest
from app.schemas.workflow import WorkflowRequest, WorkflowResponse
from app.config import Settings, get_settings
import time
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["workflow"])

@router.post("/workflow", response_model=WorkflowResponse)
async def process_workflow(
    request:WorkflowRequest,
    settings:Settings = Depends(get_settings) ):
    """
    Main entry point for all Order-to-Cash AI workflows.
    Routes to appropriate agent based on intent classification.
    """
    start_time = time.monotonic()

    try:
        response = WorkflowResponse(
            session_id = request.session_id,
            intent = "KNOWLEDGE",
            response = f"[STUB] Processing: {request.query}",
            groundedness_score = 1.0,
            latency_ms = (time.monotonic() - start_time) * 1000,
        )
        return response
    
    except Exception as e:
        logger.error(f"Workflow error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))