from typing import Dict, Any, Tuple
from app.core.logger import logger
from app.core.config import settings

class IntentClassificationModule:
    """
    HLD 3.3: Intent Classification Module
    Determines query type, complexity, confidence level, and if clarification is needed.
    Uses custom trained ML intent classifier (TF-IDF + Logistic Regression) without external LLMs.
    """
    
    async def classify(self, query: str, conversation_history: list = None, domain: str = "general") -> Tuple[str, float, str, bool]:
        """
        Returns (intent, confidence, complexity, needs_clarification)
        """
        is_retail = str(domain).lower() in ["retail", "retail_clothing"]

        # 1. For Retail Domain: Always use our custom trained ML Intent Classifier
        if is_retail:
            from app.services.intent_service import intent_service
            logger.info(f"[IntentModule] Using Custom Retail ML Intent Classifier for query: '{query}'")
            return await intent_service.classify(query, conversation_history, domain)

        # 2. For Other Domains: Check greetings and schema queries, default to SELECT
        clean_q = query.lower().strip().strip("!").strip(".")
        greetings = {"hi", "hello", "hey", "help", "good morning", "good afternoon", "hi there", "greetings"}
        if clean_q in greetings:
            return ("OFF_TOPIC", 1.0, "Simple", True)

        schema_triggers = {"schema", "tables", "columns", "what data", "show schema", "list tables"}
        if any(trig in clean_q for trig in schema_triggers):
            return ("SCHEMA_QUERY", 0.95, "Simple", False)

        # Standard analytical query across all domains
        logger.info(f"[IntentModule] Classified '{query}' as SELECT for domain '{domain}'")
        return ("SELECT", 0.95, "Medium", False)

intent_module = IntentClassificationModule()