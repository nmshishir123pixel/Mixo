"""
Narrative Generator - Executive Intelligence Brief.
Weaves ALL detections and correlations into a cohesive executive summary
with threat vectors, immediate actions, and monitoring recommendations.
"""
from app.core.config import settings
import json
import logging

logger = logging.getLogger(__name__)


class NarrativeGenerator:

    def __init__(self):
        try:
            from app.services.llm import get_langchain_llm
            self.llm = get_langchain_llm(temperature=0.6)
        except Exception:
            self.llm = None

    async def generate(self, detections: list, clusters: list, scan_metadata: dict) -> dict:
        det_summaries = []
        for d in detections:
            det_summaries.append(
                {
                    "mission": d.get("mission_name"),
                    "domain": d.get("domain"),
                    "severity": d.get("severity"),
                    "risk_score": d.get("risk_score", 0),
                    "data_count": d.get("data_count", 0),
                    "insight": str(d.get("insight") or "")[:300],
                    "is_sub_finding": d.get("depth", 0) > 0,
                }
            )

        if self.llm:
            try:
                from langchain_core.prompts import ChatPromptTemplate
                prompt = ChatPromptTemplate.from_template(
                    """You are the Chief Intelligence Officer preparing a real-time threat brief for the executive board.

SCAN OVERVIEW:
- Total missions executed: {total_missions}
- Domains covered: security, compliance, risk, operations
- Timestamp: {timestamp}

DETECTION SUMMARIES:
{detection_summaries}

THREAT CLUSTERS (cross-domain correlations):
{clusters}

Write a concise executive intelligence brief. Turn raw detections into actionable intelligence.

RESPONSE FORMAT (JSON only, no markdown):
{{
    "executive_summary": "Your platform currently faces...",
    "threat_vectors": [
        {{
            "name": "Threat name",
            "severity": "CRITICAL or HIGH or MEDIUM",
            "description": "1-2 sentence description"
        }}
    ],
    "immediate_actions": ["Action 1", "Action 2"],
    "monitoring_recommendations": ["Recommendation 1"]
}}"""
                )

                chain = prompt | self.llm
                response = await chain.ainvoke(
                    {
                        "total_missions": scan_metadata.get("total_missions", len(detections)),
                        "timestamp": scan_metadata.get("timestamp", "LIVE"),
                        "detection_summaries": json.dumps(det_summaries, indent=2, default=str),
                        "clusters": json.dumps(clusters, indent=2, default=str),
                    }
                )

                text = response.content
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()

                result = json.loads(text)

                scores = [d.get("risk_score", 0) for d in detections if d.get("risk_score")]
                top_scores = sorted(scores, reverse=True)[:5]
                overall_risk = round(sum(top_scores) / max(len(top_scores), 1)) if top_scores else 0

                result["overall_risk"] = overall_risk
                result["overall_severity"] = (
                    "CRITICAL" if overall_risk >= 75 else
                    "HIGH" if overall_risk >= 50 else
                    "MEDIUM" if overall_risk >= 25 else "LOW"
                )
                result["title"] = f"Intelligence Brief - {scan_metadata.get('timestamp', 'LIVE')}"
                return result
            except Exception as e:
                logger.warning(f"LLM Narrative generation failed ({e}); using offline summary.")

        # Offline Executive Brief Construction
        scores = [d.get("risk_score", 0) for d in detections if d.get("risk_score")]
        top_scores = sorted(scores, reverse=True)[:5]
        overall_risk = round(sum(top_scores) / max(len(top_scores), 1)) if top_scores else 15

        critical_count = len([d for d in detections if d.get("severity") in ("CRITICAL", "HIGH")])

        return {
            "title": f"Executive Intelligence Brief - {scan_metadata.get('timestamp', 'LIVE')}",
            "overall_risk": overall_risk,
            "overall_severity": "CRITICAL" if critical_count > 0 else "MEDIUM",
            "executive_summary": f"Autonomous surveillance scan completed across {len(detections)} surveillance missions. System identified {critical_count} high-priority anomalies requiring immediate operational attention.",
            "threat_vectors": [
                {
                    "name": d.get("mission_name", "Anomalous Pattern"),
                    "severity": d.get("severity", "MEDIUM"),
                    "description": str(d.get("insight") or "Operational deviation detected.")[:150]
                }
                for d in detections[:3]
            ],
            "immediate_actions": [
                "Execute automated purchase orders for low-stock SKUs.",
                "Review margin compliance on high-volume items.",
                "Audit regional store settlement discrepancy."
            ],
            "monitoring_recommendations": [
                "Maintain continuous Sentinel surveillance at 2-hour intervals.",
                "Verify live inventory feeds with live_data/ sync."
            ]
        }


narrative_generator = NarrativeGenerator()
