import asyncio
import json
import logging
from app.core.config import settings
from app.orchestration.scan_memory import scan_memory

logger = logging.getLogger(__name__)

class SentinelBrainstormer:
    def __init__(self):
        try:
            from app.services.llm import get_langchain_llm
            self.llm = get_langchain_llm(temperature=0.8)
        except Exception:
            self.llm = None

        self.schema_context = """
        ACTUAL TABLES (Retail Clothing Domain):
        - shop_sales (transaction_id, date, customer_id, shop_name, product, category, quantity, price, discount_pct, cost, profit, payment_method, city)
        - products (sku, style_name, category, size, color, unit_cost, retail_price, supplier_id, created_at)
        - inventory (sku, location, stock_count, reorder_point, last_restocked_at)
        """

    def _get_offline_missions(self) -> list:
        """High-impact offline surveillance missions grounded in live retail dataset."""
        return [
            {
                "id": "sec-001",
                "name": "Stockout Risk & Inventory Safety Baseline",
                "query": "Which products are at risk of stockout this week?",
                "domain": "security",
                "severity": "CRITICAL"
            },
            {
                "id": "sec-002",
                "name": "Payment Method Settlement Risk",
                "query": "Show sales by payment method",
                "domain": "risk",
                "severity": "MEDIUM"
            },
            {
                "id": "comp-001",
                "name": "Pricing & Margin Compliance Audit",
                "query": "Show profit by product",
                "domain": "compliance",
                "severity": "HIGH"
            },
            {
                "id": "comp-002",
                "name": "Regional Velocity & Jurisdiction Variance",
                "query": "What are the sales by city?",
                "domain": "compliance",
                "severity": "MEDIUM"
            },
            {
                "id": "ops-001",
                "name": "Store Sales Velocity & Channel Flow",
                "query": "Which shop had highest sales?",
                "domain": "operations",
                "severity": "HIGH"
            },
            {
                "id": "ops-002",
                "name": "Inventory SKU Turn Rate & Top Movers",
                "query": "Show top selling products",
                "domain": "operations",
                "severity": "MEDIUM"
            }
        ]

    async def brainstorm_missions(self, count_per_domain=2):
        if settings.USE_CUSTOM_MODELS or not self.llm:
            return self._get_offline_missions()

        try:
            from langchain_core.prompts import ChatPromptTemplate
            adaptive = scan_memory.get_adaptive_context()
            domain_weights = {"retail_clothing": count_per_domain * 4}
            total_count = sum(domain_weights.values())

            prompt = ChatPromptTemplate.from_template("""
                You are the "Sentinel Brain", an autonomous retail intelligence and surveillance agent.
                Generate dynamic audit questions based on retail inventory, sales, and supply chains.
                SCHEMA: {schema}
                TOTAL: {total_count}
                RESPONSE FORMAT (JSON only):
                [
                    {{
                        "id": "unique_string",
                        "name": "Short Mission Name",
                        "query": "The natural language question",
                        "domain": "security, compliance, risk, or operations",
                        "severity": "CRITICAL, HIGH, or MEDIUM"
                    }}
                ]
            """)

            chain = prompt | self.llm
            response = await asyncio.wait_for(
                chain.ainvoke({
                    "schema": self.schema_context,
                    "total_count": total_count,
                }),
                timeout=5.0
            )

            text = response.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            missions = json.loads(text)
            return missions if isinstance(missions, list) and len(missions) > 0 else self._get_offline_missions()
        except Exception as e:
            logger.warning(f"LLM brainstorm failed or timed out ({e}); using grounded retail surveillance missions.")
            return self._get_offline_missions()
