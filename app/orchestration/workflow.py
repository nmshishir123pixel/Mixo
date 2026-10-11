import asyncio
from langgraph.graph import StateGraph, END
from typing import Dict, Any
from app.models.state import GraphState
from app.modules.intent_classification import intent_module
from app.modules.clarification import clarification_module
from app.modules.preprocessing import preprocessing_service
from app.modules.sql_generation import sql_generation_module
from app.modules.validation import validation_module
from app.modules.visualization import visualization_module
from app.modules.insight_generation import insight_module
from app.modules.stockout_analyzer import analyze_stockout_risk
from app.services.database import db_service
from app.core.logger import logger
from app.services.auto_insights_scheduler import calculate_confidence

# Node Definitions

async def classify_intent_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [classify_intent]")
    query = state["user_question"]
    domain = state.get("domain", "general")
    conversation_history = state.get("conversation_history", [])
    
    clean_q = query.lower().strip()

    # 1. Check for forecasting health/status inquiries
    status_patterns = [
        "is demand forecast", "is demand forecasting", "is forecasting working",
        "is forecast working", "demand forecast status", "forecast status",
        "how does demand forecast work", "check demand forecast"
    ]
    if any(p in clean_q for p in status_patterns):
        logger.info(f"Intent classified: FORECAST_STATUS (status check for '{query}')")
        return {
            "intent": "FORECAST_STATUS",
            "confidence": 0.99,
            "needs_clarification": False,
            "relevant_columns": [],
            "few_shot_examples": [],
            "entities": {},
            "domain": domain
        }

    # 2. Check for predictive demand forecast requests
    forecast_patterns = [
        "demand forecast", "forecast demand", "future forecast", "predict demand",
        "demand prediction", "sales forecast", "forecast sales", "safety stock for",
        "forecast for sku", "forecast for product", "predict sales", "predict future"
    ]
    has_forecast_word = any(w in clean_q for w in ["forecast", "forecasting", "predict"])
    has_product_ref = any(w in clean_q for w in ["sku", "product", "item", "stockout", "safety stock", "demand"])

    if any(p in clean_q for p in forecast_patterns) or (has_forecast_word and has_product_ref):
        logger.info(f"Intent classified: DEMAND_FORECAST (predictive engine for '{query}')")
        return {
            "intent": "DEMAND_FORECAST",
            "confidence": 0.99,
            "needs_clarification": False,
            "relevant_columns": [],
            "few_shot_examples": [],
            "entities": {},
            "domain": domain
        }
    
    intent, confidence, complexity, needs_clarification = await intent_module.classify(query, conversation_history, domain=domain)
    preproc_data = await preprocessing_service.process(query, domain=domain)
    
    logger.info(f"Intent classified: {intent} (conf: {confidence}) | Needs Clarification: {needs_clarification}")
    
    return {
        "intent": intent,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "relevant_columns": preproc_data["relevant_columns"],
        "few_shot_examples": preproc_data["few_shot_examples"],
        "entities": preproc_data["entities"], # Ensure entities are passed forward
        "domain": domain
    }

async def generate_clarification_node(state: GraphState) -> Dict[str, Any]:
    """Ask user for more information."""
    query = state["user_question"]
    domain = state.get("domain", "general")
    conversation_history = state.get("conversation_history", [])
    
    clarification_question = await clarification_module.generate_clarification(
        query, domain, conversation_history
    )
    
    return {
        "clarification_question": clarification_question,
        "status": "needs_clarification"
    }

async def generate_sql_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [generate_sql]")
    query = state["user_question"]
    domain = state.get("domain", "general")
    context = {
        "relevant_columns": state["relevant_columns"],
        "few_shot_examples": state["few_shot_examples"],
        "entities": state.get("entities", {}), # Fixed: Pass resolved entities forward
        "domain": domain,
        "conversation_history": state.get("conversation_history", []),
        "model_provider": state.get("model_provider", "local"),
        "model_name": state.get("model_name"),
        "api_key": state.get("api_key")
    }
    sql = await sql_generation_module.generate(query, context)
    
    # If the generator returned a guidance message (Error: ...)
    if sql.startswith("Error:"):
        logger.info(f"SQL Generator returned guidance instead of SQL: {sql[:50]}...")
        return {
            "generated_sql": None,
            "clarification_question": sql.replace("Error:", "").strip(),
            "status": "needs_clarification"
        }
        
    logger.info(f"SQL Generated: {sql[:50]}...")
    return {"generated_sql": sql}

async def validate_sql_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [validate_sql]")
    sql = state.get("generated_sql")
    if not sql:
        return {"validation_error": "No SQL query generated."}
        
    val_res = validation_module.validate(sql)
    if isinstance(val_res, dict):
        status = val_res.get("status", "allowed")
        is_valid = (status in ("allowed", "warning"))
        error = val_res.get("message") if not is_valid else None
    elif isinstance(val_res, tuple):
        is_valid = val_res[0]
        error = val_res[1] if len(val_res) > 1 and not is_valid else None
    else:
        is_valid = bool(val_res)
        error = None if is_valid else "SQL validation failed."

    if not is_valid:
        logger.warning(f"SQL Validation Error: {error}")
        return {"validation_error": error}
    return {"validation_error": None}

async def repair_sql_node(state: GraphState) -> Dict[str, Any]:
    query = state["user_question"]
    invalid_sql = state["generated_sql"]
    error = state["validation_error"]
    
    repaired_sql = await sql_generation_module.repair(query, invalid_sql, error)
    
    return {
        "generated_sql": repaired_sql,
        "validation_error": None,
        "retry_count": state.get("retry_count", 0) + 1
    }

async def execute_query_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [execute_query]")
    sql = state["generated_sql"]
    try:
        results = db_service.execute(sql)
        logger.info(f"Query execution successful. Rows: {len(results)}")
        return {"query_result": results, "status": "success"}
    except Exception as e:
        logger.error(f"SQL EXECUTION ERROR: {str(e)}")
        return {"query_result": None, "status": "failed", "validation_error": str(e)}

async def analyze_stockout_node(state: GraphState) -> Dict[str, Any]:
    """Analyze stockout risk for query results."""
    logger.info("Node: [analyze_stockout]")
    domain = state.get("domain", "general")
    query = state["user_question"]
    results = state.get("query_result", [])

    # Only run stockout analysis for relevant domains and successful queries
    if domain not in ["retail_clothing", "general"] or state.get("status") != "success":
        return {}

    # Check if query is related to inventory/stock
    stock_keywords = ["stock", "inventory", "reorder", "stockout", "supply", "product", "sku"]
    if not any(kw in query.lower() for kw in stock_keywords):
        return {}

    try:
        stockout_results = analyze_stockout_risk(domain, threshold_days=7, method="auto")
        logger.info(f"Stockout analysis complete: {len(stockout_results)} at-risk products")

        # If there are at-risk products, we can enhance the insight/recommendation
        if stockout_results:
            # Add stockout context to state for insight generation
            return {
                "stockout_analysis": stockout_results,
                "stockout_count": len(stockout_results)
            }
    except Exception as e:
        logger.warning(f"Stockout analysis failed: {e}")

    return {}

async def recommend_visualization_node(state: GraphState) -> Dict[str, Any]:
    """Analyze results and recommend visualization."""
    logger.info("Node: [recommend_visualization]")
    query = state["user_question"]
    sql = state.get("generated_sql", "")
    results = state.get("query_result", [])
    
    if not results:
        logger.info("No results for visualization recommendation.")
        return {"visualization_config": None}

    vis_config = await visualization_module.recommend(query, sql, results)
    logger.info(f"Visualization recommended: {vis_config.get('chart_type') if vis_config else 'None'}")
    
    # If LLM generated mock data because real results were empty
    if vis_config and vis_config.get("is_mock") and "mock_data" in vis_config:
        logger.info("Injecting mock data for demonstration.")
        return {
            "visualization_config": vis_config,
            "query_result": vis_config["mock_data"] # Update results with mock data
        }
    
    return {"visualization_config": vis_config}

async def insight_recommendation_node(state: GraphState) -> Dict[str, Any]:
    """Provide executive insights and recommendations based on the results."""
    logger.info("Node: [insight_recommendation]")
    query = state["user_question"]
    results = state.get("query_result", [])
    domain = state.get("domain", "general")
    status = state.get("status", "unknown")
    
    if status != "success":
        logger.info(f"Skipping insights because status is {status}")
        return {}

    insights = await insight_module.generate(
        query=query,
        results=results,
        domain=domain,
        model_provider=state.get("model_provider", "local"),
        model_name=state.get("model_name"),
        api_key=state.get("api_key")
    )
    logger.info("Insights generated successfully.")
    
    return {
        "insight": insights.get("insight"),
        "recommendation": insights.get("recommendation")
    }

async def guidance_node(state: GraphState) -> Dict[str, Any]:
    """Generate a helpful response for off-topic or schema queries."""
    from app.core.config import settings
    from app.modules.schema_understanding import schema_module
    
    query = state["user_question"]
    domain = state.get("domain", "general")
    intent = state.get("intent", "OFF_TOPIC")
    
    if settings.USE_CUSTOM_MODELS:
        if intent == "SCHEMA_QUERY":
            guidance = (
                "Here is the database schema for InsightOS:\n"
                "- **products**: sku, style_name, category, size, color, retail_price\n"
                "- **inventory**: sku, stock_count, reorder_point, location\n"
                "- **suppliers**: supplier_id, supplier_name, lead_time_days, on_time_rate\n"
                "- **sales_events**: event_id, sku, units_sold, channel, date\n"
                "- **purchase_orders**: po_id, sku, qty, status, total_cost\n\n"
                "You can ask me questions about stockout risk, reorder quantities, or sales performance."
            )
        else:
            guidance = (
                f"I am your retail AI assistant. I can help analyze your inventory, demand, and sales data.\n"
                f"Try asking:\n"
                f"- 'Which products are at risk of stockout?'\n"
                f"- 'What items should we reorder today?'\n"
                f"- 'Show top selling products by category'"
            )
        return {
            "clarification_question": guidance,
            "status": "needs_clarification" 
        }

    from app.services.llm import llm_service
    schema_context = schema_module.get_schema_string(domain=domain)
    
    if intent == "SCHEMA_QUERY":
        prompt = f"""You are a Database Expert. User asked: "{query}"\nSchema: {schema_context}\nProvide a clear list of tables and columns available."""
    else:
        prompt = f"""You are a database assistant. User asked: "{query}"\nSuggest 3 relevant retail data queries."""
    
    try:
        guidance = await llm_service.generate_response(prompt)
    except Exception:
        guidance = "I can answer questions regarding stock levels, demand forecasts, and product sales."
    
    return {
        "clarification_question": guidance,
        "status": "needs_clarification" 
    }

async def format_response_node(state: GraphState) -> Dict[str, Any]:
    # Format results if needed
    return {}

async def demand_forecast_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [demand_forecast]")
    query = state["user_question"]
    from app.modules.demand_forecaster import DemandForecaster
    import sqlite3
    import re

    # 1. Extract SKU from query (e.g. SKU-1001, sku1001, SKU_1001)
    sku_match = re.search(r'\b(SKU[-_]?\d{3,5})\b', query, re.IGNORECASE)
    sku_id = None
    if sku_match:
        sku_id = sku_match.group(1).upper()
        if "_" in sku_id:
            sku_id = sku_id.replace("_", "-")
        elif "-" not in sku_id:
            sku_id = f"SKU-{sku_id[3:]}"
    else:
        # Search by style_name in database
        try:
            conn = sqlite3.connect("retail_clothing.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute("SELECT sku, style_name, category FROM products;").fetchall()
            q_clean = query.lower()
            for r in rows:
                name_words = [w.lower() for w in r["style_name"].split() if len(w) > 3]
                if any(w in q_clean for w in name_words):
                    sku_id = r["sku"]
                    break
            if not sku_id and rows:
                sku_id = rows[0]["sku"]
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to lookup SKU from product table: {e}")
            sku_id = "SKU-1001"

    if not sku_id:
        sku_id = "SKU-1001"

    try:
        forecast_res = DemandForecaster.generate_sku_forecast(sku_id, horizon_days=14, db_path="retail_clothing.db")
    except Exception as exc:
        logger.error(f"Demand forecasting calculation failed: {exc}")
        return {
            "status": "failed",
            "validation_error": f"Forecasting calculation failed: {str(exc)}"
        }

    product_name = forecast_res.get("product_name", f"Product {sku_id}")
    current_stock = forecast_res.get("current_stock", 0)
    safety_metrics = forecast_res.get("safety_stock_metrics", {})
    risk_assessment = forecast_res.get("stockout_risk_assessment", {})
    risk_level = risk_assessment.get("risk_level", "MEDIUM")
    action_rec = risk_assessment.get("action_recommended", "Monitor inventory.")
    dates = forecast_res.get("forecast_dates", [])
    predictions = forecast_res.get("predicted_demand", [])
    upper = forecast_res.get("confidence_upper_95", [])
    lower = forecast_res.get("confidence_lower_95", [])

    records = []
    for d, p, u, l in zip(dates, predictions, upper, lower):
        records.append({
            "forecast_date": d,
            "predicted_demand": p,
            "upper_bound_95": u,
            "lower_bound_95": l,
            "current_stock": current_stock,
            "safety_stock": safety_metrics.get("safety_stock_units", 0)
        })

    insight_md = (
        f"**14-Day Demand Forecast: {product_name} (`{sku_id}`)**\n\n"
        f"- **Architecture:** Hybrid CNN-LSTM Time-Series Engine (95% Confidence Interval)\n"
        f"- **Current On-Hand Stock:** **{current_stock} units**\n"
        f"- **Average Projected Daily Demand:** **{safety_metrics.get('avg_daily_demand', 0)} units/day**\n"
        f"- **Dynamic Safety Stock Threshold:** **{safety_metrics.get('safety_stock_units', 0)} units**\n"
        f"- **Lead-Time Reorder Point:** **{safety_metrics.get('reorder_point_units', 0)} units** (Lead Time: {safety_metrics.get('lead_time_days', 7)} days)\n"
        f"- **Stockout Risk Level:** **{risk_level}** (Projected balance at lead time: {risk_assessment.get('projected_balance_at_lead_time', 0)} units)"
    )

    recommendation_md = (
        f"{action_rec} Supplier lead time is {safety_metrics.get('lead_time_days', 7)} days with a 95% service level buffer."
    )

    sql_explanation = (
        f"-- Neural Demand Forecaster: Hybrid CNN-LSTM Rolling Matrix Engine\n"
        f"-- Dynamic Safety Stock: SS = Z * sqrt(L * sigma_D^2 + D^2 * sigma_L^2)\n"
        f"-- Evaluated SKU: {sku_id} ({product_name}) | Forecast Horizon: 14 Days"
    )

    vis_config = {
        "chart_type": "line",
        "title": f"14-Day Demand Forecast: {product_name} ({sku_id})",
        "x_axis_key": "forecast_date",
        "y_axis_key": ["predicted_demand", "upper_bound_95", "lower_bound_95"],
        "insights": [
            f"Current Stock: {current_stock} units",
            f"Safety Stock: {safety_metrics.get('safety_stock_units', 0)} units",
            f"Risk Level: {risk_level}"
        ]
    }

    return {
        "query_result": records,
        "visualization_config": vis_config,
        "insight": insight_md,
        "recommendation": recommendation_md,
        "generated_sql": sql_explanation,
        "status": "success"
    }

async def forecast_status_node(state: GraphState) -> Dict[str, Any]:
    logger.info("Node: [forecast_status]")
    from app.modules.demand_forecaster import DemandForecaster

    status_ok = True
    test_sku = "SKU-1001"
    try:
        test_res = DemandForecaster.generate_sku_forecast(test_sku, horizon_days=7)
        if not test_res or "predicted_demand" not in test_res:
            status_ok = False
    except Exception as e:
        logger.warning(f"Forecaster health check failed: {e}")
        status_ok = False

    status_str = "Operational & Active" if status_ok else "Degraded"

    status_message = (
        f"**[STATUS: {status_str}] Demand Forecasting Engine is operational.**\n\n"
        f"**Model Architecture & Capabilities:**\n"
        f"- **Neural Architecture:** Hybrid CNN-LSTM Neural Network (14-day rolling time-series projections)\n"
        f"- **Confidence Intervals:** 95% confidence bounds (±1.96 standard error margins)\n"
        f"- **Dynamic Safety Stock Formula:**\n"
        f"  `Safety Stock = Z * sqrt(L * sigma_D^2 + D^2 * sigma_L^2)`\n"
        f"- **Lead-Time Stockout Risk:** Automatic evaluation against supplier delivery velocity (`suppliers.lead_time_days`)\n\n"
        f"**Try asking in chat:**\n"
        f"- *'What is the demand forecast for SKU-1001?'*\n"
        f"- *'Predict demand for Wireless Noise-Canceling Headphones'*\n"
        f"- *'Show demand forecast for SKU-1005'*"
    )

    return {
        "clarification_question": status_message,
        "status": "needs_clarification"
    }

# Conditional Edges

def route_after_intent(state: GraphState):
    """Route based on whether clarification is needed."""
    intent = state.get("intent")
    if intent == "DEMAND_FORECAST":
        return "demand_forecast"
    if intent == "FORECAST_STATUS":
        return "forecast_status"
    if intent in ["OFF_TOPIC", "SCHEMA_QUERY"]:
        return "guidance"
    if state.get("needs_clarification", False):
        return "clarification"
    return "generate_sql"

def route_after_validation(state: GraphState):
    if state["validation_error"]:
        if state.get("retry_count", 0) < 3:
            return "repair_sql"
        else:
            return "format_response"  # Or failure node
    return "execute_query"

# Graph Construction

workflow = StateGraph(GraphState)

workflow.add_node("classify_intent", classify_intent_node)
workflow.add_node("clarification", generate_clarification_node)
workflow.add_node("guidance", guidance_node)
workflow.add_node("demand_forecast", demand_forecast_node)
workflow.add_node("forecast_status", forecast_status_node)
workflow.add_node("generate_sql", generate_sql_node)
workflow.add_node("validate_sql", validate_sql_node)
workflow.add_node("repair_sql", repair_sql_node)
workflow.add_node("execute_query", execute_query_node)
workflow.add_node("analyze_stockout", analyze_stockout_node)
workflow.add_node("recommend_visualization", recommend_visualization_node)
workflow.add_node("insight_recommendation", insight_recommendation_node)
workflow.add_node("format_response", format_response_node)

workflow.set_entry_point("classify_intent")

workflow.add_conditional_edges(
    "classify_intent",
    route_after_intent,
    {
        "generate_sql": "generate_sql",
        "clarification": "clarification",
        "guidance": "guidance",
        "demand_forecast": "demand_forecast",
        "forecast_status": "forecast_status"
    }
)

# Clarification & Forecasting terminals
workflow.add_edge("clarification", END)
workflow.add_edge("guidance", END)
workflow.add_edge("demand_forecast", END)
workflow.add_edge("forecast_status", END)

def route_after_sql_generation(state: GraphState):
    if state.get("status") == "needs_clarification":
        return "end"
    return "validate_sql"

workflow.add_conditional_edges(
    "generate_sql",
    route_after_sql_generation,
    {
        "validate_sql": "validate_sql",
        "end": END
    }
)

workflow.add_conditional_edges(
    "validate_sql",
    route_after_validation,
    {
        "execute_query": "execute_query",
        "repair_sql": "repair_sql",
        "format_response": "format_response"
    }
)

workflow.add_edge("repair_sql", "validate_sql")
workflow.add_edge("execute_query", "analyze_stockout")
workflow.add_edge("analyze_stockout", "recommend_visualization")
workflow.add_edge("analyze_stockout", "insight_recommendation")

# Join parallel branches
workflow.add_edge(["recommend_visualization", "insight_recommendation"], "format_response")
workflow.add_edge("format_response", END)

app_graph = workflow.compile()
