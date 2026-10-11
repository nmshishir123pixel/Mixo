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
    
    async def generate(
        self,
        query: str,
        results: List[Dict[str, Any]],
        domain: str = "general",
        model_provider: str = "local",
        model_name: str = None,
        api_key: str = None
    ) -> Dict[str, str]:
        """
        Generates insight and recommendation based on data.
        Supports:
        - 'local': Custom retail template engine (instant, offline)
        - 'nvidia': NVIDIA NIM Cloud API
        - 'chatgpt' / 'openai': ChatGPT Omni
        """
        provider = str(model_provider or "local").lower().strip()
        logger.info(f"Generating insights: provider='{provider}', domain='{domain}', rows={len(results)}")
        
        if not results:
            return {
                "insight": "No data found matching your query criteria.",
                "recommendation": "Review date range filters or verify inventory and transaction records in live_data."
            }

        is_retail = str(domain).lower() in ["retail", "retail_clothing"]

        # 1. RETAIL DOMAIN: Use deterministic retail insight generator (instant 0ms, mathematically exact)
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
                logger.info("[Instant Retail Insights] Generated domain insights in 0ms.")
                return retail_insights

        # 2. NVIDIA NIM OR CHATGPT / OPENAI PROVIDER (For general domains)
        if provider in ("nvidia", "chatgpt", "openai"):
            from app.services.llm import llm_service
            import asyncio
            sample_results = results[:5] 
            results_str = json.dumps(sample_results)

            prompt = f"""You are the Chief Intelligence Officer (CIO) for an enterprise operating in the '{domain}' domain.
User Question: "{query}"
Data Results ({len(sample_results)} rows): {results_str}

Analyze the data and provide:
1. Executive finding (1-2 sentences with exact numbers from the data).
2. Actionable recommendation (1 clear next step).

Format response as JSON ONLY:
{{"insight": "Executive finding with numbers.", "recommendation": "Actionable next step."}}"""

            try:
                target_provider = "nvidia" if provider == "nvidia" else ("chatgpt" if provider in ("chatgpt", "openai") else "nvidia")
                response = await asyncio.wait_for(
                    llm_service.generate_response_for_provider(
                        prompt=prompt,
                        provider=target_provider,
                        model_name=model_name,
                        api_key=api_key,
                        temperature=0.0,
                        max_tokens=1024,
                        stop=["```\n"]
                    ),
                    timeout=20.0
                )
                
                # Parse JSON
                cleaned_resp = response.replace("```json", "").replace("```", "").strip()
                start_idx = cleaned_resp.find("{")
                end_idx = cleaned_resp.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    cleaned_resp = cleaned_resp[start_idx:end_idx+1]
                    
                data = json.loads(cleaned_resp)
                insight_val = data.get("insight", "")
                if isinstance(insight_val, dict):
                    insight_val = " ".join(f"{k.replace('_', ' ').title()}: {v}." for k, v in insight_val.items())
                rec_val = data.get("recommendation", "")
                if isinstance(rec_val, dict):
                    rec_val = " ".join(f"{k.replace('_', ' ').title()}: {v}." for k, v in rec_val.items())

                if insight_val and rec_val:
                    return {
                        "insight": str(insight_val),
                        "recommendation": str(rec_val)
                    }
            except asyncio.TimeoutError:
                logger.warning(f"⚡ LLM ({provider}) insight generation exceeded 10s timeout. Using local rule engine fallback.")
            except Exception as e:
                logger.warning(f"LLM ({provider}) Insight Generation failed ({e}), using rule engine fallback...")

        # 2. LOCAL DOMAIN / FALLBACK: Use deterministic retail insight generator (instant 0ms)
        from app.services.insight_generator import insight_generator_service
        from app.services.intent_service import intent_service
        retail_intent = intent_service.get_retail_intent(query)
        retail_insights = insight_generator_service.generate(
            query=query,
            results=results,
            domain="retail_clothing" if is_retail else domain,
            retail_intent=retail_intent
        )
        if retail_insights and retail_insights.get("insight"):
            return retail_insights

        return {
            "insight": "Data retrieved successfully.",
            "recommendation": "Review retrieved metrics."
        }

insight_module = InsightGenerationModule()
