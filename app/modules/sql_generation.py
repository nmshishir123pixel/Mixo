from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.core.config import settings

class SQLGenerationModule:
    """
    HLD 3.4: SQL Generation Module
    Generates SQL from user natural language query and context.
    Uses Rule-based Pattern Matching & Predefined Templates when custom models are enabled (zero external LLM dependencies).
    """
    
    async def generate(self, query: str, context: Dict[str, Any]) -> str:
        """
        Generates SQL based on query and context (schema, few-shot, domain, etc.)
        """
        domain = context.get("domain", "general")
        is_retail = str(domain).lower() in ["retail", "retail_clothing"]

        # 1. For Retail Domain: Use our custom-trained model & rule engine
        if is_retail:
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            
            retail_intent = context.get("retail_intent")
            if not retail_intent:
                retail_intent = intent_service.get_retail_intent(query)
                
            entities = context.get("entities", {})
            resolved_entities = entities.get("resolved_entities", {}) if isinstance(entities, dict) else {}
            
            generated_sql = sql_generator.generate(
                query=query,
                retail_intent=retail_intent,
                entities=resolved_entities,
                domain="retail_clothing"
            )
            if generated_sql and not generated_sql.startswith("Error:"):
                logger.info(f"[Custom Retail Model] Generated SQL: {generated_sql}")
                return generated_sql
            logger.info("[Custom Retail Model] No direct template match, falling back to LLM...")

        # 2. For All Other Domains (or retail fallback): Use LLM API (NVIDIA NIM / OpenAI) with Live Schema
        from app.services.llm import llm_service
        if llm_service.provider:
            from app.services.database import db_service
            
            live_schema = db_service.get_schema_info()
            schema_dict = {}
            for item in live_schema:
                parts = item.split('.')
                if len(parts) == 2:
                    t, c = parts
                    if t not in schema_dict:
                        schema_dict[t] = []
                    schema_dict[t].append(c)
                
            live_schema_str = "DATABASE SCHEMA:\n"
            for table, cols in schema_dict.items():
                live_schema_str += f"Table: {table} | Columns: {', '.join(cols)}\n"

            prompt = f"""You are an expert Chief Data Scientist and SQL engineer for the '{domain}' business domain.
Generate a valid SQLite query to answer the user's natural language question.
Only return valid executable SQL without markdown or explanation.

{live_schema_str}

Business Domain: {domain}
User Request: {query}
SQL Query:"""
            try:
                response = await llm_service.generate_response(prompt, model_name=settings.SQL_MODEL)
                cleaned_sql = response.replace("```sql", "").replace("```", "").replace(";", "").strip() + ";"
                logger.info(f"LLM [{llm_service.provider}] Generated SQL for domain '{domain}': {cleaned_sql}")
                return cleaned_sql
            except Exception as e:
                logger.warning(f"LLM SQL Generation failed ({e}), using rule engine fallback...")

        # 3. Fallback Pattern Matching
        from app.ml_models.sql_generator.rule_engine import sql_generator
        from app.services.intent_service import intent_service
        
        retail_intent = context.get("retail_intent") or intent_service.get_retail_intent(query)
        entities = context.get("entities", {})
        resolved_entities = entities.get("resolved_entities", {}) if isinstance(entities, dict) else {}
        
        return sql_generator.generate(
            query=query,
            retail_intent=retail_intent,
            entities=resolved_entities,
            domain=domain
        )

    async def repair(self, query: str, invalid_sql: str, error: str) -> str:
        """
        Repairs invalid SQL.
        """
        if settings.USE_CUSTOM_MODELS:
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            retail_intent = intent_service.get_retail_intent(query)
            logger.info(f"[SQL Repair] Using template fallback for query: '{query}'")
            return sql_generator.generate(query, retail_intent)

        from app.services.llm import llm_service
        prompt = f"""Fix the SQLite query for: "{query}"\nInvalid SQL: {invalid_sql}\nError: {error}\nReturn ONLY corrected SQL."""
        try:
            response = await llm_service.generate_response(prompt)
            return response.replace("```sql", "").replace("```", "").strip()
        except Exception as e:
            logger.error(f"SQL Repair Error: {e}")
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            return sql_generator.generate(query, intent_service.get_retail_intent(query))

sql_generation_module = SQLGenerationModule()
