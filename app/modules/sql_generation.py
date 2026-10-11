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
    
    _sql_cache: Dict[str, str] = {}

    COMPACT_RETAIL_SCHEMA = """TABLE products (
    sku TEXT PRIMARY KEY,
    style_name TEXT,
    category TEXT,
    size TEXT,
    color TEXT,
    unit_cost REAL,
    retail_price REAL,
    supplier_id TEXT
)

TABLE inventory (
    sku TEXT PRIMARY KEY,
    location TEXT,
    stock_count INTEGER,
    reorder_point INTEGER,
    last_restocked_at TEXT
)

TABLE shop_sales (
    transaction_id TEXT PRIMARY KEY,
    date TEXT,
    shop_id TEXT,
    shop_name TEXT,
    category TEXT,
    city TEXT,
    product TEXT,
    quantity INTEGER,
    unit_price REAL,
    sales REAL,
    cost REAL,
    profit REAL,
    payment_method TEXT,
    customer_type TEXT
)

TABLE sales_events (
    event_id TEXT PRIMARY KEY,
    sku TEXT,
    units_sold INTEGER,
    sale_date TEXT,
    channel TEXT
)

TABLE suppliers (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT,
    lead_time_days INTEGER,
    on_time_rate REAL,
    country TEXT
)

TABLE purchase_orders (
    id INTEGER PRIMARY KEY,
    po_number TEXT,
    product_id TEXT,
    product_name TEXT,
    quantity INTEGER,
    supplier_id TEXT,
    supplier_name TEXT,
    status TEXT,
    unit_cost REAL,
    total_cost REAL,
    total_amount REAL,
    created_at TEXT
)

TABLE warehouses (
    warehouse_id TEXT PRIMARY KEY,
    name TEXT,
    city TEXT,
    country TEXT,
    capacity_units INTEGER
)"""

    def _get_detailed_schema(self, domain: str = "retail_clothing") -> str:
        """Fetch compact, domain-relevant schema to minimize LLM prompt token size and TTFT."""
        if str(domain).lower() in ["retail", "retail_clothing", "general"]:
            return self.COMPACT_RETAIL_SCHEMA
        try:
            from app.services.database import db_service
            rows = db_service.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%';")
            relevant_names = {'products', 'inventory', 'shop_sales', 'sales_events', 'suppliers', 'purchase_orders', 'warehouses'}
            schemas = [r.get("sql") for r in rows if r.get("name") in relevant_names and r.get("sql")]
            if schemas:
                return "\n\n".join(schemas)
        except Exception as e:
            logger.warning(f"Failed to fetch DDL schema from sqlite_master: {e}")
        return self.COMPACT_RETAIL_SCHEMA

    @staticmethod
    def _extract_sql_query(raw_text: str) -> str:
        """Cleanly extract raw SQL query from LLM output, handling markdown fences and conversational wrappers."""
        text = (raw_text or "").strip()
        # 1. If inside markdown block ```sql ... ```
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p_clean = p.strip()
                if p_clean.lower().startswith("sql"):
                    p_clean = p_clean[3:].strip()
                if "select " in p_clean.lower() or "with " in p_clean.lower():
                    text = p_clean
                    break
        
        # 2. Check for explicit prefix 'query:\s*(SELECT|WITH)' or 'sql:\s*(SELECT|WITH)'
        import re
        m_explicit = re.search(r'(?:query|sql):\s*(\b(?:SELECT|WITH)\b.+?)(?:;|$)', text, re.IGNORECASE | re.DOTALL)
        if m_explicit:
            text = m_explicit.group(1)

        # 3. Candidate evaluation using SQLite EXPLAIN QUERY PLAN validation
        from app.services.database import db_service
        from sqlalchemy import text as sa_text
        indices = [m.start() for m in re.finditer(r'\b(?:SELECT|WITH)\b', text, re.IGNORECASE)]
        valid_candidate = None
        for idx in reversed(indices):
            cand = text[idx:].strip()
            semi = cand.find(';')
            if semi != -1:
                cand = cand[:semi+1]
            else:
                cand = cand.rstrip() + ';'
            lines = [line.strip() for line in cand.splitlines() if line.strip() and not line.strip().startswith("--")]
            cand_clean = " ".join(lines)
            try:
                with db_service.engine.connect() as conn:
                    conn.execute(sa_text(f"EXPLAIN QUERY PLAN {cand_clean}"))
                    valid_candidate = cand_clean
                    break
            except Exception:
                continue

        if valid_candidate:
            cleaned = valid_candidate
        else:
            # 4. Fallback to standard substring extraction
            m_cte = re.search(r'\bWITH\s+[a-zA-Z0-9_]+\s+AS\s*\(.+', text, re.IGNORECASE | re.DOTALL)
            m_select = re.search(r'\bSELECT\s+[a-zA-Z0-9_.*].+', text, re.IGNORECASE | re.DOTALL)
            if m_cte:
                text = m_cte.group(0)
            elif m_select:
                text = m_select.group(0)

            semi_pos = text.find(";")
            if semi_pos != -1:
                text = text[:semi_pos + 1]
            else:
                text = text.rstrip() + ";"

            lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("--")]
            cleaned = " ".join(lines)

        # 5. Fix misordered ORDER BY / LIMIT before GROUP BY
        if " group by " in cleaned.lower() and " order by " in cleaned.lower():
            match = re.search(r'(ORDER BY\s+[^;]+?\s+LIMIT\s+\d+)\s+(GROUP BY\s+[^;]+)', cleaned, re.IGNORECASE)
            if match:
                order_limit = match.group(1)
                group_by = match.group(2)
                cleaned = cleaned[:match.start()] + group_by + " " + order_limit + cleaned[match.end():]

        if not cleaned.endswith(";"):
            cleaned += ";"
        return cleaned

    @staticmethod
    def _sanitize_stockout_dates(query: str, sql: str) -> str:
        """
        Guardrail: If the query asks for stockout risk, out of stock, or low stock reorder,
        and the LLM added an erroneous date filter on `last_restocked_at` (due to words like 'this week' or 'today'),
        strip the erroneous condition so real inventory data is returned.
        """
        import re
        q_low = query.lower()
        is_stockout_query = any(kw in q_low for kw in [
            "stockout", "out of stock", "low stock", "run out", "at risk", "reorder"
        ])
        is_restock_query = any(kw in q_low for kw in ["restocked", "restock date", "last restock"])

        if is_stockout_query and not is_restock_query and "last_restocked_at" in sql.lower():
            # Pattern 1: ... AND i.last_restocked_at >= ...
            cleaned = re.sub(
                r'\s+AND\s+([a-zA-Z0-9_]+\.)?last_restocked_at\s*[><=].*?(?=[;\sGROUPORDERLIMIT)]|$)',
                '',
                sql,
                flags=re.IGNORECASE
            )
            # Pattern 2: WHERE i.last_restocked_at >= ... AND ...
            cleaned = re.sub(
                r'WHERE\s+([a-zA-Z0-9_]+\.)?last_restocked_at\s*[><=].*?\s+AND\s+',
                'WHERE ',
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = cleaned.strip()
            if not cleaned.endswith(";"):
                cleaned += ";"
            logger.info(f"[Guardrail] Cleaned erroneous date filter from stockout SQL: {sql} -> {cleaned}")
            return cleaned
        return sql

    async def generate(self, query: str, context: Dict[str, Any]) -> str:
        """
        Generates SQL based on query and context with high-speed execution optimizations.
        Supports:
        - 'local': Custom retail rule engine (0ms, offline)
        - 'nvidia': NVIDIA NIM Cloud API (Nemotron-3-Super 120B)
        - 'chatgpt' / 'openai': ChatGPT (GPT-4o / GPT-4o-mini)
        """
        import asyncio
        domain = context.get("domain", "general")
        model_provider = str(context.get("model_provider") or "local").lower().strip()
        model_name = context.get("model_name")
        api_key = context.get("api_key")
        is_retail = str(domain).lower() in ["retail", "retail_clothing", "general"]

        # Fast Cache Lookup: If identical question was asked recently, return instant 0ms SQL
        cache_key = f"{domain}:{model_provider}:{query.strip().lower()}"
        if cache_key in self._sql_cache:
            cached_sql = self._sql_cache[cache_key]
            logger.info(f"[Instant SQL Cache Hit] Returning cached SQL for: '{query}'")
            return cached_sql

        logger.info(f"SQL Generation request: provider='{model_provider}', domain='{domain}', query='{query}'")

        # 1. LOCAL MODEL: Use our custom-trained model & rule engine
        if model_provider == "local" and is_retail:
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            
            retail_intent = context.get("retail_intent") or intent_service.get_retail_intent(query)
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
                self._sql_cache[cache_key] = generated_sql
                return generated_sql
            logger.info("[Custom Retail Model] No direct template match, falling back to LLM...")

        # 2. NVIDIA NIM OR CHATGPT / OPENAI PROVIDER
        if model_provider in ("nvidia", "chatgpt", "openai") or not is_retail:
            from app.services.llm import llm_service
            from app.services.database import db_service

            detailed_schema = self._get_detailed_schema(domain=domain)

            system_prompt = f"""You are an elite SQL engineer for an enterprise retail database running on SQLite.
Business Domain: {domain}

EXACT DATABASE SCHEMA:
{detailed_schema}

Critical SQLite Rules:
1. Return ONLY the raw SQLite query ending with a semicolon. Do NOT write markdown fences (```), comments (--), conversational preamble, or explanations.
2. Select descriptive columns:
   - For products / catalog: Always SELECT p.style_name, p.sku, p.category, p.retail_price (plus unit_cost or size when asked).
   - For inventory stock levels: SELECT p.style_name, p.sku, i.stock_count, i.location, i.reorder_point FROM products p JOIN inventory i ON p.sku = i.sku.
   - For out-of-stock items: Condition is strictly WHERE i.stock_count <= 0.
   - For low stock / stockout risk / reorder needed: Condition is strictly WHERE i.stock_count <= i.reorder_point.
   - CRITICAL DATE RULES:
     * INVENTORY IS CURRENT SNAPSHOT: Questions asking "Which products are at risk of stockout this week / today / this month / soon / right now?", "Which products are out of stock this week?", or "reorder recommendations" refer strictly to CURRENT inventory on-hand levels. NEVER add a date condition on i.last_restocked_at! Condition is strictly WHERE i.stock_count <= i.reorder_point (or WHERE i.stock_count <= 0 for out of stock).
     * RESTOCK QUERIES: Only filter by `last_restocked_at` when the user specifically asks when items were restocked (e.g. "Which products were restocked in the past 30 days?").
     * RECENT TRANSACTIONS / SALES: For "recent sales" or "latest transactions", use `ORDER BY date DESC LIMIT 15` (on shop_sales) or `ORDER BY sale_date DESC LIMIT 15` (on sales_events).
   - For dead stock: SELECT p.sku, p.style_name, i.stock_count FROM products p JOIN inventory i ON p.sku = i.sku WHERE i.stock_count > 0 AND p.sku NOT IN (SELECT sku FROM sales_events WHERE sale_date >= date('now', '-90 days')).
   - For listing individual transactions: SELECT transaction_id, date, product, shop_name, city, quantity, sales, profit, payment_method FROM shop_sales.
   - For purchase orders: Query purchase_orders table. Columns: po_number, product_name, quantity, supplier_name, status, total_amount.
   - For warehouses: Query warehouses table. Columns: warehouse_id, name, city, country, capacity_units.
   - For suppliers: Query suppliers table. Columns: supplier_name, lead_time_days, on_time_rate, country.
3. Case-Insensitive String Comparisons:
   - In SQLite, string comparisons are case-sensitive. ALWAYS use case-insensitive matching: LOWER(col) = LOWER('val') or col LIKE 'val'.
4. Correct Table Joins:
   - products and inventory: ON products.sku = inventory.sku
   - products and suppliers: ON products.supplier_id = suppliers.supplier_id OR products.supplier_id = suppliers.supplier_name
   - products and shop_sales: ON LOWER(products.style_name) = LOWER(shop_sales.product)
   - products and purchase_orders: ON products.sku = purchase_orders.product_id
   - products and sales_events: ON products.sku = sales_events.sku
5. Ordering & Limits:
   - "Highest", "top", "most", "best", "max" -> ORDER BY ... DESC
   - "Lowest", "least", "cheapest", "min", "ascending" -> ORDER BY ... ASC
   - If user asks for top N (e.g. "top 5"), add LIMIT N.
6. SQLite Syntax & Clause Order:
   - Clauses MUST strictly appear in this order: SELECT ... FROM ... [JOIN ...] [WHERE ...] [GROUP BY ...] [HAVING ...] [ORDER BY ...] [LIMIT ...].
   - NEVER place ORDER BY or LIMIT before GROUP BY!"""

            user_prompt = f"User Question: {query}\nSQL Query:"

            try:
                target_provider = "nvidia" if model_provider == "nvidia" else ("chatgpt" if model_provider in ("chatgpt", "openai") else "nvidia")
                response = await asyncio.wait_for(
                    llm_service.generate_response_for_provider(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        provider=target_provider,
                        model_name=model_name,
                        api_key=api_key,
                        temperature=0.0,
                        max_tokens=1024,
                        stop=[";\n", ";\r\n"]
                    ),
                    timeout=22.0
                )
                
                cleaned_sql = self._extract_sql_query(response)
                cleaned_sql = self._sanitize_stockout_dates(query, cleaned_sql)
                logger.info(f"LLM [{target_provider}] Generated SQL: {cleaned_sql}")

                # Test execution to ensure validity
                try:
                    from sqlalchemy import text
                    with db_service.engine.connect() as conn:
                        test_exec = conn.execute(text(cleaned_sql))
                        rows_data = test_exec.fetchall() if test_exec.returns_rows else []
                    logger.info(f"LLM SQL validated successfully ({len(rows_data)} rows returned).")
                    self._sql_cache[cache_key] = cleaned_sql
                    return cleaned_sql
                except Exception as val_e:
                    logger.warning(f"LLM Generated SQL execution check failed: {val_e}. Attempting self-repair...")
                    repair_prompt = f"""Fix this invalid SQLite query:
Error: {val_e}
Invalid SQL: {cleaned_sql}
Database Schema:
{detailed_schema}
User Question: {query}
Return ONLY the corrected raw SQLite query ending with semicolon:"""
                    try:
                        repair_res = await asyncio.wait_for(
                            llm_service.generate_response_for_provider(
                                prompt=repair_prompt,
                                provider=target_provider,
                                model_name=model_name,
                                api_key=api_key,
                                temperature=0.0,
                                max_tokens=1024,
                                stop=[";\n"]
                            ),
                            timeout=15.0
                        )
                        repaired_sql = self._extract_sql_query(repair_res)
                        repaired_sql = self._sanitize_stockout_dates(query, repaired_sql)
                        test_repair = db_service.execute(repaired_sql)
                        logger.info(f"Self-repaired SQL executed successfully ({len(test_repair)} rows).")
                        self._sql_cache[cache_key] = repaired_sql
                        return repaired_sql
                    except Exception as rep_err:
                        logger.warning(f"Self-repair also failed ({rep_err}), falling back to intelligent rule engine...")

            except asyncio.TimeoutError:
                logger.warning(f"[NVIDIA NIM API] Exceeded latency limit for '{query}'. Auto-switching to instant local engine fallback.")
            except Exception as e:
                logger.warning(f"LLM ({model_provider}) SQL Generation failed ({e}), falling back to rule engine...")

        # 3. Fallback Pattern Matching (Offline Rule Engine)
        from app.ml_models.sql_generator.rule_engine import sql_generator
        from app.services.intent_service import intent_service
        
        retail_intent = context.get("retail_intent") or intent_service.get_retail_intent(query)
        entities = context.get("entities", {})
        resolved_entities = entities.get("resolved_entities", {}) if isinstance(entities, dict) else {}
        
        fallback_sql = sql_generator.generate(
            query=query,
            retail_intent=retail_intent,
            entities=resolved_entities,
            domain=domain
        )
        return fallback_sql

    async def repair(self, query: str, invalid_sql: str, error: str) -> str:
        """
        Repairs invalid SQL using the configured provider or rule fallback.
        """
        from app.services.llm import llm_service
        from app.services.database import db_service
        prompt = f"""Fix the SQLite query for: "{query}"\nInvalid SQL: {invalid_sql}\nError: {error}\nSchema:\n{self.COMPACT_RETAIL_SCHEMA}\nReturn ONLY corrected SQL ending with semicolon."""
        try:
            response = await llm_service.generate_response(prompt)
            clean = self._extract_sql_query(response)
            clean = self._sanitize_stockout_dates(query, clean)
            db_service.execute(clean)
            return clean
        except Exception as e:
            logger.error(f"SQL Repair Error: {e}")
            from app.ml_models.sql_generator.rule_engine import sql_generator
            from app.services.intent_service import intent_service
            return sql_generator.generate(query, intent_service.get_retail_intent(query))

sql_generation_module = SQLGenerationModule()
