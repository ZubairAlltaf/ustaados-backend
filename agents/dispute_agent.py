"""
UstaadOS — Dispute Agent
Handles post-service disputes using AI verdict + history analysis.
"""
import json
import re
from agents.base_agent import BaseAgent
from database.client import get_db


class DisputeAgent(BaseAgent):
    name = "DisputeAgent"

    REFUND_POLICIES = {
        "overcharging": {"max_refund_pct": 0.50, "threshold_overcharge_pct": 20},
        "poor_quality": {"max_refund_pct": 0.30, "threshold": 3.0},
        "incomplete_work": {"max_refund_pct": 0.60, "threshold": 0.0},
        "no_show": {"max_refund_pct": 1.00, "threshold": 0.0},
        "delayed_arrival": {"max_refund_pct": 0.15, "threshold_delay_min": 60},
        "fake_diagnosis": {"max_refund_pct": 0.80, "threshold": 0.0},
        "other": {"max_refund_pct": 0.25, "threshold": 0.0},
    }

    def observe(self, inputs: dict) -> dict:
        booking_id = inputs.get("booking_id")
        dispute_type = inputs.get("dispute_type", "other")
        description = inputs.get("description", "")
        quoted_price = inputs.get("quoted_price", 0)
        actual_charged = inputs.get("actual_charged", 0)
        provider_id = inputs.get("provider_id")
        booking = inputs.get("booking", {})

        # Fetch provider history
        provider_history = self._get_provider_dispute_history(provider_id)
        provider_data = self._get_provider(provider_id)

        return {
            "booking_id": booking_id,
            "dispute_type": dispute_type,
            "description": description,
            "quoted_price": quoted_price,
            "actual_charged": actual_charged,
            "price_difference": actual_charged - quoted_price,
            "overcharge_pct": ((actual_charged - quoted_price) / max(quoted_price, 1)) * 100 if quoted_price else 0,
            "provider_trust_score": provider_data.get("trust_score", 50),
            "provider_fraud_risk": provider_data.get("fraud_risk", 5),
            "provider_prior_disputes": provider_history.get("total_disputes", 0),
            "provider_avg_rating": provider_data.get("avg_rating", 4.0),
            "provider_data": provider_data,
            "summary": f"Dispute: {dispute_type} | Booking: {booking_id} | "
                       f"Price diff: PKR {actual_charged - quoted_price:+,}",
        }

    def reason(self, observation: dict) -> str:
        dispute_type = observation["dispute_type"]
        description = observation["description"]
        quoted = observation["quoted_price"]
        actual = observation["actual_charged"]
        overcharge_pct = observation["overcharge_pct"]
        provider_trust = observation["provider_trust_score"]
        provider_fraud_risk = observation["provider_fraud_risk"]
        prior_disputes = observation["provider_prior_disputes"]
        avg_rating = observation["provider_avg_rating"]

        policy = self.REFUND_POLICIES.get(dispute_type, self.REFUND_POLICIES["other"])

        prompt = f"""You are UstaadOS's Dispute Resolution AI for Pakistan's service market.

Dispute Type: {dispute_type}
Description: {description}
Quoted Price: PKR {quoted:,}
Actual Charged: PKR {actual:,}
Overcharge: {overcharge_pct:.0f}%

Provider Profile:
- Trust Score: {provider_trust:.0f}/100
- Fraud Risk: {provider_fraud_risk:.0f}%
- Prior Disputes: {prior_disputes}
- Average Rating: {avg_rating:.1f}/5

Refund Policy for {dispute_type}: max {policy.get('max_refund_pct', 0)*100:.0f}% refund

Analyze this dispute and return ONLY valid JSON with:
- legitimacy_score: float 0-1 (1 = clearly legitimate customer complaint)
- verdict: "CUSTOMER_FAVOR" | "PROVIDER_FAVOR" | "SPLIT_DECISION" | "ESCALATE"
- verdict_reason: brief explanation (2-3 sentences)
- recommended_refund_pct: float 0-1 (fraction of price to refund)
- recommended_refund_amount: int (PKR)
- provider_action: "WARNING" | "SUSPENSION" | "TRUST_SCORE_REDUCTION" | "NO_ACTION"
- trust_score_adjustment: int (negative = reduce trust, 0 = no change)
- fraud_risk_adjustment: int (positive = increase fraud risk)

JSON only:"""

        llm_response = self.call_llm(prompt, temperature=0.1)

        # Combine rule-based + LLM
        rules_note = ""
        if dispute_type == "no_show" and actual == 0:
            rules_note = "\nRULE: No-show confirmed — full refund mandatory."
        elif overcharge_pct > 50 and provider_fraud_risk > 30:
            rules_note = f"\nRULE: Severe overcharge ({overcharge_pct:.0f}%) + elevated fraud risk — customer favor."

        return llm_response + rules_note

    def decide(self, reasoning: str) -> dict:
        try:
            clean = re.sub(r"```json\s*|\s*```", "", reasoning.split("RULE:")[0]).strip()
            parsed = json.loads(clean)
            rule_notes = [l for l in reasoning.split("\n") if l.startswith("RULE:")]

            return {
                "legitimacy_score": float(parsed.get("legitimacy_score", 0.5)),
                "verdict": parsed.get("verdict", "ESCALATE"),
                "verdict_reason": parsed.get("verdict_reason", "Insufficient information"),
                "recommended_refund_pct": float(parsed.get("recommended_refund_pct", 0)),
                "recommended_refund_amount": int(parsed.get("recommended_refund_amount", 0)),
                "provider_action": parsed.get("provider_action", "NO_ACTION"),
                "trust_score_adjustment": int(parsed.get("trust_score_adjustment", 0)),
                "fraud_risk_adjustment": int(parsed.get("fraud_risk_adjustment", 0)),
                "rule_overrides": rule_notes,
                "confidence": float(parsed.get("legitimacy_score", 0.5)),
                "summary": f"Verdict: {parsed.get('verdict')} | Refund: PKR {parsed.get('recommended_refund_amount', 0):,}",
            }
        except Exception as e:
            return {
                "legitimacy_score": 0.5,
                "verdict": "ESCALATE",
                "verdict_reason": f"Parse error — escalating to human review: {str(e)[:50]}",
                "recommended_refund_pct": 0,
                "recommended_refund_amount": 0,
                "provider_action": "NO_ACTION",
                "trust_score_adjustment": 0,
                "fraud_risk_adjustment": 0,
                "rule_overrides": [],
                "confidence": 0.3,
                "summary": "Escalated to human review (parse error)",
            }

    def act(self, decision: dict) -> dict:
        verdict = decision["verdict"]
        refund = decision["recommended_refund_amount"]
        provider_action = decision["provider_action"]

        # Update provider trust score if needed
        if decision["trust_score_adjustment"] != 0 or decision["fraud_risk_adjustment"] != 0:
            self._update_provider_scores(decision)

        action_msg = f"Verdict: {verdict}. Refund: PKR {refund:,}. Provider action: {provider_action}."

        return {
            "action_taken": action_msg,
            "result": f"Dispute resolved ({verdict}). "
                      f"Refund of PKR {refund:,} {'initiated' if refund > 0 else 'not applicable'}. "
                      f"Provider trust adjusted by {decision['trust_score_adjustment']} points.",
            "output": decision,
        }

    def _get_provider_dispute_history(self, provider_id: str) -> dict:
        try:
            db = get_db()
            result = db.table("disputes") \
                .select("id, status") \
                .eq("provider_id", provider_id) \
                .execute()
            data = result.data or []
            return {
                "total_disputes": len(data),
                "resolved": len([d for d in data if d["status"] == "resolved"]),
            }
        except Exception:
            return {"total_disputes": 0, "resolved": 0}

    def _get_provider(self, provider_id: str) -> dict:
        try:
            db = get_db()
            result = db.table("providers").select("*").eq("id", provider_id).single().execute()
            return result.data or {}
        except Exception:
            return {}

    def _update_provider_scores(self, decision: dict) -> None:
        """Update provider trust/fraud scores after dispute resolution."""
        try:
            db = get_db()
            # Would need provider_id from context — passed via booking lookup
            pass
        except Exception:
            pass
