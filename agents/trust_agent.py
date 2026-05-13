"""
UstaadOS — Trust Agent
The most important differentiator.
Predicts technician reliability, trustworthiness, fraud risk,
and cancellation probability for a given booking context.
"""
from agents.base_agent import BaseAgent
from config import (
    TRUST_HIGH, TRUST_MEDIUM, FRAUD_RISK_THRESHOLD, CANCELLATION_RISK_THRESHOLD
)


class TrustAgent(BaseAgent):
    name = "TrustAgent"

    def observe(self, inputs: dict) -> dict:
        providers = inputs.get("providers", [])
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        weather_temp = inputs.get("weather_temp", 35.0)

        return {
            "providers": providers,
            "provider_count": len(providers),
            "service_type": intent.get("service_type", ""),
            "urgency": intent.get("urgency_level", "medium"),
            "severity_score": severity.get("severity_score", 2.5),
            "weather_temp": weather_temp,
            "is_heatwave": weather_temp > 40,
            "summary": f"Evaluating trust for {len(providers)} providers | "
                       f"Urgency: {intent.get('urgency_level')} | "
                       f"Heatwave: {weather_temp > 40}",
        }

    def reason(self, observation: dict) -> str:
        providers = observation["providers"]
        urgency = observation["urgency"]
        severity = observation["severity_score"]
        is_heatwave = observation["is_heatwave"]

        # Score each provider using deterministic formula
        scored_providers = []
        rejected_providers = []
        reasons = []

        for p in providers:
            trust_score = float(p.get("trust_score", 50))
            cancellation_rate = float(p.get("cancellation_rate", 10))
            fraud_risk = float(p.get("fraud_risk", 5))
            avg_rating = float(p.get("avg_rating", 3.5))
            punctuality = float(p.get("punctuality_score", 75))
            completion_rate = float(p.get("completion_rate", 85))
            repeat_ratio = float(p.get("repeat_customer_ratio", 20))
            review_count = int(p.get("review_count", 0))

            # Trust rejection logic
            rejection_reasons = []

            # High cancellation is disqualifying for urgent/critical jobs
            if urgency in ["high", "critical"] and cancellation_rate > CANCELLATION_RISK_THRESHOLD:
                rejection_reasons.append(
                    f"Cancellation rate {cancellation_rate:.0f}% too high for {urgency} urgency"
                )

            # Fraud risk always disqualifying above threshold
            if fraud_risk > FRAUD_RISK_THRESHOLD:
                rejection_reasons.append(f"Fraud risk score {fraud_risk:.0f}% exceeds threshold")

            # Very low trust score
            if trust_score < TRUST_MEDIUM and urgency == "critical":
                rejection_reasons.append(f"Trust score {trust_score:.0f} insufficient for critical job")

            if rejection_reasons:
                rejected_providers.append({
                    "provider_id": p.get("id"),
                    "name": p.get("name"),
                    "rejection_reasons": rejection_reasons,
                })
                reasons.append(
                    f"REJECTED {p.get('name')}: {'; '.join(rejection_reasons)}"
                )
                continue

            # ── Composite Trust Score (weighted) ──────────────────────────
            # trust_score base: 35%
            # cancellation safety: 25%
            # rating quality: 20%
            # punctuality: 10%
            # completion reliability: 10%

            cancellation_safety = max(0, 100 - cancellation_rate)
            composite = (
                trust_score * 0.35
                + cancellation_safety * 0.25
                + (avg_rating / 5.0 * 100) * 0.20
                + punctuality * 0.10
                + completion_rate * 0.10
            )

            # Heatwave penalty — reduce availability pool
            if is_heatwave and p.get("workload", 0) >= 4:
                composite *= 0.8
                reasons.append(f"REDUCED {p.get('name')}: High workload during heatwave")

            # Bonus for review volume (credibility)
            if review_count >= 100:
                composite = min(100, composite * 1.05)

            # Penalty for low review count (unknown entity)
            if review_count < 10:
                composite *= 0.85

            trust_verdict = (
                "HIGH_TRUST" if composite >= TRUST_HIGH else
                "MEDIUM_TRUST" if composite >= TRUST_MEDIUM else
                "LOW_TRUST"
            )

            scored_providers.append({
                **p,
                "composite_trust": round(composite, 2),
                "trust_verdict": trust_verdict,
                "cancellation_safety": round(cancellation_safety, 2),
                "is_recommended": composite >= TRUST_MEDIUM,
            })

            reasons.append(
                f"SCORED {p.get('name')}: composite={composite:.1f} | "
                f"verdict={trust_verdict} | cancel_risk={cancellation_rate:.0f}%"
            )

        return "\n".join(reasons) + f"\n\nFINAL: {len(scored_providers)} approved, {len(rejected_providers)} rejected."

    def decide(self, reasoning: str) -> dict:
        # The reasoning string is our internal reasoning — extract the counts
        lines = reasoning.split("\n")
        approved = [l for l in lines if l.startswith("SCORED")]
        rejected = [l for l in lines if l.startswith("REJECTED")]

        return {
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "reasoning_log": reasoning,
            "confidence": 0.95,
            "summary": f"{len(approved)} providers approved, {len(rejected)} rejected by Trust Agent",
        }

    def act(self, decision: dict) -> dict:
        return {
            "action_taken": f"Trust screening complete: {decision['approved_count']} approved, "
                            f"{decision['rejected_count']} rejected",
            "result": f"Trusted provider pool ready. {decision['approved_count']} candidates forwarded to Matching Agent.",
            "output": decision,
        }

    def score_providers(self, providers: list, intent: dict, severity: dict, weather_temp: float) -> tuple[list, list]:
        """
        Public method: Returns (approved_providers, rejected_providers)
        with composite_trust scores attached.
        """
        urgency = intent.get("urgency_level", "medium")
        is_heatwave = weather_temp > 40

        approved = []
        rejected = []

        for p in providers:
            trust_score = float(p.get("trust_score", 50))
            cancellation_rate = float(p.get("cancellation_rate", 10))
            fraud_risk = float(p.get("fraud_risk", 5))
            avg_rating = float(p.get("avg_rating", 3.5))
            punctuality = float(p.get("punctuality_score", 75))
            completion_rate = float(p.get("completion_rate", 85))
            review_count = int(p.get("review_count", 0))

            rejection_reasons = []

            if urgency in ["high", "critical"] and cancellation_rate > CANCELLATION_RISK_THRESHOLD:
                rejection_reasons.append(
                    f"{cancellation_rate:.0f}% cancellation rate — too risky for {urgency} urgency"
                )
            if fraud_risk > FRAUD_RISK_THRESHOLD:
                rejection_reasons.append(f"Fraud risk {fraud_risk:.0f}% exceeds safety threshold")
            if trust_score < TRUST_MEDIUM and urgency == "critical":
                rejection_reasons.append(f"Trust score {trust_score:.0f} insufficient for critical priority")

            if rejection_reasons:
                rejected.append({**p, "rejection_reasons": rejection_reasons})
                continue

            cancellation_safety = max(0, 100 - cancellation_rate)
            composite = (
                trust_score * 0.35
                + cancellation_safety * 0.25
                + (avg_rating / 5.0 * 100) * 0.20
                + punctuality * 0.10
                + completion_rate * 0.10
            )

            if is_heatwave and p.get("workload", 0) >= 4:
                composite *= 0.8
            if review_count >= 100:
                composite = min(100, composite * 1.05)
            if review_count < 10:
                composite *= 0.85

            approved.append({
                **p,
                "composite_trust": round(composite, 2),
                "trust_verdict": (
                    "HIGH_TRUST" if composite >= TRUST_HIGH else
                    "MEDIUM_TRUST" if composite >= TRUST_MEDIUM else
                    "LOW_TRUST"
                ),
                "cancellation_safety": round(cancellation_safety, 2),
                "rejection_reasons": [],
            })

        return approved, rejected
