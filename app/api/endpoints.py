from fastapi import APIRouter, HTTPException
from app.models.state import QueryRequest, QueryResponse
from app.alert_system.metric_models import MetricRequest, MetricResponse
from app.alert_system.metric_workflow import metric_app_graph
from app.orchestration.workflow import app_graph
from app.core.logger import logger
from app.core.config import settings
from app.api.stockout_endpoints import router as stockout_router

router = APIRouter()

router.include_router(stockout_router)

from app.models.state import QueryRequest, QueryResponse, ChatGPTVerifyRequest

@router.post("/query", response_model=QueryResponse)
async def query_database(request: QueryRequest):
    """
    Process a natural language query through the NL2SQL pipeline.
    Supports conversational clarification flow and model selection (Local, NVIDIA NIM, ChatGPT).
    """
    logger.info(f"Incoming query: {request.query} | Domain: {request.domain} | Model Provider: {request.model_provider}")
    initial_state = {
        "user_question": request.query,
        "domain": request.domain,
        "conversation_history": request.conversation_history,
        "model_provider": request.model_provider or "local",
        "model_name": request.model_name,
        "api_key": request.api_key,
        "retry_count": 0
    }

    # Run the graph
    result = await app_graph.ainvoke(initial_state)
    logger.info(f"Graph execution status: {result.get('status')} for query: {request.query}")

    # Check if clarification is needed
    if result.get("status") == "needs_clarification":
        return QueryResponse(
            sql=None,
            results=None,
            status="needs_clarification",
            clarification_question=result.get("clarification_question"),
            metadata={
                "model_provider": request.model_provider or "local",
                "model_name": request.model_name
            },
            is_final=False
        )

    # Check for validation errors
    if result.get("validation_error") and not result.get("query_result"):
        logger.warning(f"Validation failure for query: {request.query} | Error: {result['validation_error']}")
        return QueryResponse(
            sql=result.get("generated_sql"),
            results=None,
            status="failed",
            error=result["validation_error"],
            metadata={
                "model_provider": request.model_provider or "local",
                "model_name": request.model_name
            },
            is_final=True
        )

    # Success - SQL generated and executed
    logger.info(f"Query success! {len(result.get('query_result', []))} rows returned.")
    resolved_model_name = request.model_name or (
        getattr(settings, "MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b") if request.model_provider == "nvidia" 
        else ("gpt-4o" if request.model_provider in ("chatgpt", "openai") else "local_retail_engine")
    )
    return QueryResponse(
        sql=result.get("generated_sql"),
        results=result.get("query_result"),
        visualization_config=result.get("visualization_config"),
        insight=result.get("insight"),
        recommendation=result.get("recommendation"),
        status="success",
        metadata={
            "model_provider": request.model_provider or "local",
            "model_name": resolved_model_name
        },
        is_final=True
    )

@router.post("/auth/chatgpt-verify")
async def verify_chatgpt_auth(req: ChatGPTVerifyRequest):
    """
    Test and verify user-provided OpenAI ChatGPT credentials.
    """
    from app.services.llm import llm_service
    res = await llm_service.verify_chatgpt_credentials(api_key=req.api_key, model_name=req.model or "gpt-4o")
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to connect to OpenAI."))
    return res

@router.post("/auth/nvidia-verify")
async def verify_nvidia_auth():
    """
    Test and verify NVIDIA NIM configuration.
    """
    from app.services.llm import llm_service
    res = await llm_service.verify_nvidia_credentials()
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to connect to NVIDIA NIM."))
    return res

@router.post("/alert", response_model=MetricResponse)
async def create_alert(request: MetricRequest):
    """
    Process a request to create a data metric/alert.
    """
    logger.info(f"Relaying alert request to Metric Workflow: {request.query}")

    initial_state = {
        "user_query": request.query,
        "domain": request.domain,
        "conversation_history": request.conversation_history,
        "metric": {},
        "status": "pending",
        "explanation": ""
    }

    result = await metric_app_graph.ainvoke(initial_state)

    return MetricResponse(
        status=result.get("status", "failed"),
        metric=result.get("metric"),
        explanation=result.get("explanation", ""),
        clarification_question=result.get("clarification_question")
    )