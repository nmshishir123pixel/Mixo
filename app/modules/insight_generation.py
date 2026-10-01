import json
from typing import Dict, Any, List
from app.core.logger import logger
from app.core.config import settings

class InsightGenerationModule:
    """
    HLD Section 5: Decision Support & Action Recommendations
    Analyzes query results to provide executive-level insights and actionable recommendations.
    Uses Rule-Based Template Engine when custom models are enabled (zero external LLM dependencies).
    """
    
    async def generate(self, query: str, results: List[Dict[str, Any]], domain: str = "general") -> Dict[str, str]:
        """
        Generates insight and recommendation based on data.
        """
        logger.info(f"Generating insights for {len(results)} rows in domain: {domain}")
        if not results:
            return {
                "insight": "No data found to analyze.",
                "recommendation": "Try broadening your search criteria or checking if the data for this period is available."
            }

        is_retail = str(domain).lower() in ["retail", "retail_clothing"]

        # 1. For Retail Domain: Use our custom retail insight generator
        if is_retail:
            from app.services.insight_generator import insight_generator_service
            from app.services.intent_service import intent_service
            retail_intent = intent_service.get_retail_intent(query)
            retail_insights = insight_generator_service.generate(
                query=query,
                results=results,
                domain="retail_clothing",
                retail_intent=retail_intent
            )
            if retail_insights and retail_insights.get("insight"):
                logger.info("[Custom Retail Model] Generated domain insights.")
                return retail_insights

        # 2. For All Other Domains (or retail fallback): Use LLM API (NVIDIA NIM / OpenAI)
        from app.services.llm import llm_service
        if llm_service.provider:
            sample_results = results[:25] 
            results_str = json.dumps(sample_results, indent=2)

            prompt = f"""You are the Chief Intelligence Officer (CIO) for an enterprise operating in the '{domain}' domain.
User Question: "{query}"
Data Results ({len(sample_results)} sample rows of {len(results)} total):
{results_str}

Analyze these metrics strictly from a {domain} industry perspective. Provide:
1. "insight": 2-3 sentence executive analysis highlighting findings, metrics, and trends.
2. "recommendation": 1-2 concrete, high-impact tactical actions to execute.

Format your response as a JSON object:
{{
  "insight": "...",
  "recommendation": "..."
}}"""
            try:
                response = await llm_service.generate_response(prompt, model_name=settings.DISCOVERY_MODEL)
                response = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(response)
                return {
                    "insight": str(data.get("insight", "Insight generated based on data metrics.")),
                    "recommendation": str(data.get("recommendation", "Continue monitoring these trends."))
                }
            except Exception as e:
                logger.warning(f"LLM Insight Generation failed ({e}), using rule engine fallback...")

        # 3. Rule-based Insight Generation Fallback
        from app.services.insight_generator import insight_generator_service
        from app.services.intent_service import intent_service
        retail_intent = intent_service.get_retail_intent(query)
        return insight_generator_service.generate(
            query=query,
            results=results,
            domain=domain,
            retail_intent=retail_intent
        )

insight_module = InsightGenerationModule()
