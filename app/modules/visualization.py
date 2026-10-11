from typing import List, Dict, Any, Optional

class VisualizationModule:
    """
    Analyzes query results and recommends the best visualization type with
    intuitive, human-friendly titles, smart label selection, and dual-metric support.
    """
    
    async def recommend(self, query: str, sql: str, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Determines the best chart type and configuration using deterministic local heuristics in 0ms.
        """
        if not results:
            return None
            
        columns = list(results[0].keys())
        return self._heuristic_fallback(columns, results, query.lower())
            
    def _heuristic_fallback(self, columns: List[str], results: List[Dict[str, Any]], query_lower: str = "") -> Dict[str, Any]:
        """Intelligent heuristic visualization recommender."""
        # Detect numeric columns
        numeric_cols = [
            c for c in columns 
            if any(isinstance(r.get(c), (int, float)) for r in results[:5])
        ]
        
        def is_date_column(c: str) -> bool:
            cl = c.lower()
            if any(k in cl for k in ["date", "time", "timestamp"]):
                return True
            if cl.endswith("_at") or cl.startswith("at_"):
                return True
            parts = cl.split("_")
            return any(k in parts for k in ["day", "month", "year", "quarter"])

        date_cols = [c for c in columns if is_date_column(c)]
        label_cols = [c for c in columns if c not in numeric_cols]
        
        if not numeric_cols:
            return {"chart_type": "table", "title": "Data Results"}

        # Single row or aggregate overview without label breakdown: present clean table
        if len(results) == 1 or len(label_cols) == 0:
            return {
                "chart_type": "table",
                "title": "Business Summary Metrics",
                "label": "Summary",
                "description": "Aggregate summary metrics"
            }

        # 1. Special Case: Inventory / Stockout Analysis (Current Stock vs Reorder Point)
        if "current_stock" in columns and "reorder_point" in columns:
            x_key = "product" if "product" in columns else ("sku" if "sku" in columns else (label_cols[0] if label_cols else columns[0]))
            return {
                "chart_type": "bar",
                "title": "Current Stock vs Safety Threshold by Product",
                "x_axis_key": x_key,
                "y_axis_key": ["current_stock", "reorder_point"],
                "label": "Stock Comparison",
                "description": "Side-by-side comparison of current inventory levels against safety reorder points"
            }

        # 2. Reorder Recommendations
        if "recommended_reorder_qty" in columns or "recommended_restock_units" in columns:
            qty_col = "recommended_reorder_qty" if "recommended_reorder_qty" in columns else "recommended_restock_units"
            x_key = "product" if "product" in columns else ("sku" if "sku" in columns else (label_cols[0] if label_cols else columns[0]))
            y_keys = [qty_col]
            if "current_stock" in columns:
                y_keys.append("current_stock")
            return {
                "chart_type": "bar",
                "title": "Recommended Reorder Quantities by Product",
                "x_axis_key": x_key,
                "y_axis_key": y_keys,
                "label": "Reorder Quantity",
                "description": "Recommended replenishment units needed per product"
            }

        # 3. Intelligent X-axis Selection (Prioritizing high-cardinality identifying entities)
        def score_label_col(col: str) -> float:
            col_l = col.lower()
            unique_vals = len(set(str(r.get(col, "")) for r in results))
            # Heavily penalize constant columns (e.g. category = 'General' across all rows)
            if len(results) > 1 and unique_vals <= 1:
                return -100.0
            
            score = unique_vals * 2.0
            if col_l in ["product", "style_name", "item_name"]:
                score += 80.0
            elif col_l in ["shop_name", "store_name", "store", "shop"]:
                score += 70.0
            elif col_l in ["city", "location", "region"]:
                score += 60.0
            elif col_l in ["date", "month", "year"]:
                score += 50.0
            elif col_l in ["category", "dept", "department"]:
                score += 30.0
            elif col_l in ["payment_method", "payment_mode"]:
                score += 25.0
            elif col_l in ["customer_type"]:
                score += 20.0
            elif col_l in ["sku"]:
                score += 15.0
            return score

        scored_labels = sorted(label_cols, key=score_label_col, reverse=True)
        x_key = date_cols[0] if date_cols else (scored_labels[0] if scored_labels else columns[0])

        # 4. Intelligent Y-axis Selection based on intent and query keywords
        y_key = None
        if any(kw in query_lower for kw in ["profit", "margin"]):
            for c in ["total_profit", "profit", "net_profit"]:
                if c in numeric_cols:
                    y_key = c
                    break
        elif any(kw in query_lower for kw in ["sales", "revenue"]):
            for c in ["total_sales", "total_revenue", "sales", "revenue"]:
                if c in numeric_cols:
                    y_key = c
                    break
        elif any(kw in query_lower for kw in ["unit", "quantity", "volume", "sold", "count"]):
            for c in ["total_units_sold", "quantity", "num_transactions", "total_orders"]:
                if c in numeric_cols:
                    y_key = c
                    break

        if not y_key:
            priority_metrics = ["total_sales", "total_profit", "total_units_sold", "sales", "profit", "quantity", "current_stock"]
            for pm in priority_metrics:
                if pm in numeric_cols:
                    y_key = pm
                    break
            if not y_key:
                y_key = numeric_cols[0]

        # 5. Determine Chart Type
        if date_cols and x_key in date_cols:
            chart_type = "line"
        elif len(results) <= 6 and x_key in ["category", "payment_method", "customer_type", "city"]:
            chart_type = "pie"
        else:
            chart_type = "bar"

        # 6. Format Friendly Title
        def friendly_name(key: str) -> str:
            replacements = {
                "total_units_sold": "Units Sold",
                "total_sales": "Sales Revenue",
                "total_revenue": "Total Revenue",
                "total_profit": "Net Profit",
                "current_stock": "Current Stock",
                "reorder_point": "Safety Threshold",
                "units_deficit": "Stock Deficit",
                "shop_name": "Store",
                "city": "City",
                "product": "Product",
                "category": "Category",
                "payment_method": "Payment Method",
                "customer_type": "Customer Type"
            }
            if key in replacements:
                return replacements[key]
            return key.replace("_", " ").title()

        title = f"{friendly_name(y_key)} by {friendly_name(x_key)}"

        return {
            "chart_type": chart_type,
            "title": title,
            "x_axis_key": x_key,
            "y_axis_key": y_key,
            "label": friendly_name(y_key),
            "description": f"Analysis showing {friendly_name(y_key)} broken down by {friendly_name(x_key)}"
        }

visualization_module = VisualizationModule()
