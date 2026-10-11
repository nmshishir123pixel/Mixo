"""
Insight Generator — Rule-Based Template Engine
================================================
Replaces LLM-based insight generation with deterministic templates.
Produces Finding -> Insight -> Recommended Action output grounded in live retail data.
"""

import json
from typing import Dict, Any, List
from app.core.logger import logger


class InsightGeneratorService:
    """
    Rule-based insight generator using templates per intent type.
    Produces executive-level insights without external LLM calls.
    """

    def generate(
        self,
        query: str,
        results: List[Dict[str, Any]],
        domain: str = "general",
        retail_intent: str = None,
    ) -> Dict[str, str]:
        """
        Generate insights from query results using rule-based templates.
        """
        if not results:
            return {
                "insight": "No data found matching your query criteria.",
                "recommendation": "Try broadening your search or check if data for this period is available.",
            }

        row_count = len(results)
        query_lower = query.lower()

        # Auto-detect intent from query if not provided
        if retail_intent is None:
            retail_intent = self._detect_intent(query_lower)

        # Route to appropriate template
        if retail_intent == "stockout_risk" or any(kw in query_lower for kw in ["stockout", "out of stock", "risk"]):
            return self._stockout_insight(results, row_count)
        elif retail_intent == "reorder_recommendation" or any(kw in query_lower for kw in ["reorder", "restock"]):
            return self._reorder_insight(results, row_count)
        elif any(kw in query_lower for kw in ["profit", "margin", "cost"]):
            return self._profit_insight(results, row_count)
        elif any(kw in query_lower for kw in ["shop", "store", "city", "location", "payment", "customer"]):
            return self._sales_insight(results, row_count, query_lower)
        elif retail_intent == "sales_analysis" or any(kw in query_lower for kw in ["sales", "revenue", "sold", "selling", "top"]):
            return self._sales_insight(results, row_count, query_lower)
        elif retail_intent == "inventory_status" or any(kw in query_lower for kw in ["inventory", "stock"]):
            return self._inventory_insight(results, row_count)
        else:
            return self._general_insight(results, row_count, query_lower)

    def _detect_intent(self, query_lower: str) -> str:
        """Simple keyword-based intent detection for template routing."""
        if any(kw in query_lower for kw in ["stockout", "risk", "out of stock", "low stock", "run out"]):
            return "stockout_risk"
        elif any(kw in query_lower for kw in ["reorder", "purchase order", "restock", "order"]):
            return "reorder_recommendation"
        elif any(kw in query_lower for kw in ["profit", "margin", "cost"]):
            return "profit_analysis"
        elif any(kw in query_lower for kw in ["sales", "revenue", "sold", "selling", "top", "shop", "city", "payment"]):
            return "sales_analysis"
        elif any(kw in query_lower for kw in ["inventory", "stock", "warehouse", "catalog"]):
            return "inventory_status"
        return "general_query"

    def _stockout_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate crystal-clear, plain-English stockout insights for retail operators."""
        # 1. Check if results contain real inventory fields
        is_inventory_data = any("current_stock" in r or "stock_count" in r for r in results)

        if is_inventory_data:
            at_risk = []
            safe = []
            total_deficit = 0

            for r in results:
                name = r.get("product") or r.get("style_name") or r.get("sku") or "Product"
                stock = int(r.get("current_stock") if "current_stock" in r else r.get("stock_count", 0))
                reorder = int(r.get("reorder_point", 0))
                deficit = int(r.get("units_deficit") if "units_deficit" in r else max(0, reorder - stock))
                risk = str(r.get("risk_level", "")).upper()

                if stock <= reorder or deficit > 0 or "RISK" in risk or "STOCK" in risk:
                    at_risk.append({
                        "name": name,
                        "sku": r.get("sku", ""),
                        "stock": stock,
                        "reorder": reorder,
                        "deficit": max(deficit, 0),
                        "risk": risk or "HIGH RISK"
                    })
                    total_deficit += max(deficit, 0)
                else:
                    safe.append(name)

            if not at_risk:
                return {
                    "insight": (
                        "✅ All monitored products have healthy inventory levels! "
                        f"None of the {count} products in the catalog are currently below their safety threshold."
                    ),
                    "recommendation": (
                        "1. Continue regular daily sales monitoring.\n"
                        "2. Standard replenishment schedules are operating normally."
                    ),
                }

            # Build simple plain-English bullet list
            bullets = []
            for item in at_risk[:5]:
                sku_str = f" ({item['sku']})" if item['sku'] else ""
                urgency = "🔴 Urgent" if item['stock'] <= 5 else "⚠️ Low Stock"
                bullets.append(
                    f"{urgency}: {item['name']}{sku_str} — Only {item['stock']} units left in stock "
                    f"(Safety target: {item['reorder']}, Shortage: {item['deficit']} units)"
                )
            bullets_text = "\n".join(bullets)

            most_critical = min(at_risk, key=lambda x: x["stock"])

            return {
                "insight": (
                    f"⚠️ Found {len(at_risk)} product(s) at immediate risk of running out of stock this week:\n\n"
                    f"{bullets_text}\n\n"
                    f"📦 Total replenishment needed: {total_deficit} units across all low-stock items to reach safe inventory levels."
                ),
                "recommendation": (
                    f"1. Place urgent restock orders for {len(at_risk)} items ({total_deficit} units total) immediately.\n"
                    f"2. Prioritize '{most_critical['name']}' as it has the lowest inventory ({most_critical['stock']} units remaining).\n"
                    f"3. Expedite delivery with your suppliers to avoid out-of-stock lost sales."
                ),
            }

        # 2. Fallback to sales-velocity data (shop_sales)
        critical_items = []
        for r in results[:5]:
            name = r.get("product") or r.get("style_name") or r.get("sku") or "Product"
            units = r.get("total_units_sold") or r.get("quantity") or 0
            rev = r.get("total_sales") or r.get("sales") or 0
            critical_items.append(f"• {name}: {units} units sold (₹{rev:,.2f} revenue)")

        top_item = results[0].get("product", "Top product")
        items_str = "\n".join(critical_items[:4])

        return {
            "insight": (
                f"⚡ Demand Velocity Analysis (Top {min(count, 4)} Fast-Selling Products):\n\n"
                f"{items_str}\n\n"
                f"'{top_item}' has the highest sales demand right now. Because these products sell the fastest, they carry the highest risk of stocking out if not replenished frequently."
            ),
            "recommendation": (
                f"1. Check warehouse inventory levels immediately for '{top_item}'.\n"
                f"2. Keep a 2-week extra safety buffer for these fast-selling items.\n"
                f"3. Schedule frequent reorder cycles with suppliers for top-selling categories."
            ),
        }

    def _reorder_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate clear reorder recommendations with concrete units and cost."""
        total_qty = 0
        total_cost = 0.0
        reorder_list = []

        for r in results:
            name = r.get("product") or r.get("style_name") or r.get("sku") or "Product"
            qty = r.get("recommended_reorder_qty") or r.get("suggested_reorder_qty") or r.get("recommended_restock_units") or r.get("reorder_qty", 0)
            cost = r.get("estimated_unit_cost") or r.get("unit_cost", 25.0)
            cur = r.get("current_stock")
            total_qty += int(qty)
            total_cost += float(qty) * float(cost)
            stock_info = f" (Current Stock: {cur})" if cur is not None else ""
            reorder_list.append(f"• {name}{stock_info}: Order {int(qty)} units (~₹{float(qty)*float(cost):,.2f})")

        items_str = "\n".join(reorder_list[:4])
        top_item = results[0].get("product", "Top item")

        return {
            "insight": (
                f"📋 Replenishment Summary: {count} product(s) recommended for reordering.\n\n"
                f"{items_str}\n\n"
                f"📦 Total Recommended Order: {total_qty} units.\n"
                f"💰 Total Estimated Procurement Cost: ₹{total_cost:,.2f}."
            ),
            "recommendation": (
                f"1. Submit purchase orders for {total_qty} units across {count} items.\n"
                f"2. Prioritize '{top_item}' to maintain uninterrupted customer fulfillment.\n"
                f"3. Consolidate orders to reduce freight and shipping costs."
            ),
        }

    @staticmethod
    def _extract_num(row: dict, keywords: list, default: float = 0.0) -> float:
        if not isinstance(row, dict):
            return default
        for k in keywords:
            if k in row and row[k] is not None:
                try: return float(row[k])
                except (ValueError, TypeError): pass
        for k, v in row.items():
            if v is not None and any(kw in str(k).lower() for kw in keywords):
                try: return float(v)
                except (ValueError, TypeError): pass
        return default

    @staticmethod
    def _extract_name(row: dict, default: str = "Item") -> str:
        if not isinstance(row, dict):
            return default
        for k in ["product", "style_name", "shop_name", "city", "category", "sku", "name", "channel"]:
            if k in row and row[k]:
                return str(row[k])
        for k, v in row.items():
            if isinstance(v, str) and not any(kw in k.lower() for kw in ["id", "date", "status"]):
                return str(v)
        return default

    def _profit_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate profit & margin specific insights in plain language."""
        top = results[0] if results else {}
        top_name = self._extract_name(top, "Top Item")
        top_profit = self._extract_num(top, ["profit", "net_profit", "margin"])
        
        total_profit = sum(self._extract_num(r, ["profit", "net_profit", "margin"]) for r in results)
        total_sales = sum(self._extract_num(r, ["sales", "revenue", "retail_price"]) for r in results)
        overall_margin = (total_profit / max(total_sales, 1.0)) * 100 if total_sales > 0 else 0.0

        top_items = []
        for r in results[:4]:
            name = self._extract_name(r, "Item")
            p = self._extract_num(r, ["profit", "net_profit", "margin"])
            top_items.append(f"• {name}: ₹{p:,.2f} net profit")
        items_str = "\n".join(top_items)

        return {
            "insight": (
                f"💰 Profitability Overview across {count} record(s):\n\n"
                f"{items_str}\n\n"
                f"🏆 Top Profit Generator: '{top_name}' with ₹{top_profit:,.2f} in profit.\n"
                f"📊 Total Revenue: ₹{total_sales:,.2f} | Total Net Profit: ₹{total_profit:,.2f} (Average Margin: {overall_margin:.1f}%)."
            ),
            "recommendation": (
                f"1. Feature '{top_name}' prominently on storefront and campaigns to drive higher profits.\n"
                f"2. Maintain healthy profit margins above 25% by negotiating supplier volume discounts.\n"
                f"3. Review low-margin products for potential pricing or cost optimization."
            ),
        }

    def _sales_insight(self, results: List[dict], count: int, query: str) -> Dict[str, str]:
        """Generate sales and revenue insights in plain, intuitive language."""
        top = results[0] if results else {}
        top_name = self._extract_name(top, "Top Performer")
        top_units = int(self._extract_num(top, ["units_sold", "quantity", "units", "count"]))
        top_rev = self._extract_num(top, ["sales", "revenue", "amount", "retail_price"])

        total_units = sum(int(self._extract_num(r, ["units_sold", "quantity", "units", "count"])) for r in results)
        total_rev = sum(self._extract_num(r, ["sales", "revenue", "amount", "retail_price"]) for r in results)

        leaders = []
        for r in results[:4]:
            name = self._extract_name(r, "Item")
            units = int(self._extract_num(r, ["units_sold", "quantity", "units", "count"]))
            rev = self._extract_num(r, ["sales", "revenue", "amount", "retail_price"])
            if units > 0:
                leaders.append(f"• {name}: {units} units sold (₹{rev:,.2f})")
            else:
                leaders.append(f"• {name}: ₹{rev:,.2f} total revenue")
        leaders_str = "\n".join(leaders)

        unit_str = f" with {top_units} units sold" if top_units > 0 else ""
        vol_str = f"💵 Total Volume: {total_units} units | " if total_units > 0 else ""

        return {
            "insight": (
                f"📈 Sales Performance Summary ({count} entries found):\n\n"
                f"{leaders_str}\n\n"
                f"🌟 Top Performer: '{top_name}'{unit_str} (₹{top_rev:,.2f}).\n"
                f"{vol_str}Total Revenue: ₹{total_rev:,.2f}."
            ),
            "recommendation": (
                f"1. Keep stock ready for '{top_name}' to meet strong ongoing customer demand.\n"
                f"2. Apply successful promotional strategies from top products across other catalog items.\n"
                f"3. Monitor weekly sales velocity to catch new consumer trends early."
            ),
        }

    def _inventory_insight(self, results: List[dict], count: int) -> Dict[str, str]:
        """Generate clear inventory status summary."""
        total_stock = sum(int(r.get("current_stock") or r.get("stock_count") or 0) for r in results)
        low_count = sum(
            1 for r in results
            if int(r.get("current_stock") or r.get("stock_count") or 0) <= int(r.get("reorder_point") or 0)
        )
        healthy_count = len(results) - low_count

        return {
            "insight": (
                f"📦 Warehouse Inventory Snapshot ({count} items tracked):\n\n"
                f"• Total Units in Stock: {total_stock} units\n"
                f"• Healthy Stock: {healthy_count} product(s) ✅\n"
                f"• Low / Reorder Needed: {low_count} product(s) ⚠️\n\n"
                + (f"Overall inventory status is good, but {low_count} items need replenishment." if low_count > 0 else "Overall inventory status is healthy across all catalog items.")
            ),
            "recommendation": (
                "1. Check the low-stock items and generate purchase orders before they run out.\n"
                "2. Conduct periodic warehouse cycle counts to verify physical stock matches system numbers.\n"
                "3. Set automated reorder alerts for high-turnover products."
            ),
        }

    def _general_insight(self, results: List[dict], count: int, query: str) -> Dict[str, str]:
        """Generate general insights for unspecified intents."""
        if results:
            columns = list(results[0].keys())
            col_str = ", ".join(columns[:6])
        else:
            col_str = "N/A"

        return {
            "insight": (
                f"Query returned {count} records matching '{query}'. "
                f"Columns included: {col_str}."
            ),
            "recommendation": (
                "1. Explore specific aggregations like top selling products, profit margins, or stockout alerts.\n"
                "2. Use targeted entity queries (e.g. by product, city, or category) for deeper analysis."
            ),
        }


# Singleton instance
insight_generator_service = InsightGeneratorService()
