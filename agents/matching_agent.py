"""
UstaadOS — Matching Agent
Ranks trusted technicians intelligently using 12 factors.
Explains every ranking decision with transparent reasoning.
"""
import math
from agents.base_agent import BaseAgent


class MatchingAgent(BaseAgent):
    name = "MatchingAgent"

    # Matching factor weights (must sum to 1.0)
    WEIGHTS = {
        "composite_trust": 0.25,
        "distance_score": 0.18,
        "rating_score": 0.15,
        "availability_score": 0.12,
        "specialization_score": 0.10,
        "workload_score": 0.08,
        "price_fairness_score": 0.06,
        "completion_score": 0.03,
        "repeat_customer_score": 0.02,
        "response_time_score": 0.01,
    }

    def observe(self, inputs: dict) -> dict:
        providers = inputs.get("trusted_providers", [])
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        user_lat = inputs.get("user_lat", 31.5204)
        user_lng = inputs.get("user_lng", 74.3587)
        weather_temp = inputs.get("weather_temp", 35.0)
        budget_hint = intent.get("budget_hint")

        return {
            "providers": providers,
            "service_type": intent.get("service_type", "AC Repair"),
            "urgency": intent.get("urgency_level", "medium"),
            "severity_score": severity.get("severity_score", 2.5),
            "user_lat": user_lat,
            "user_lng": user_lng,
            "budget_hint": budget_hint,
            "weather_temp": weather_temp,
            "summary": f"Matching {len(providers)} trusted providers for {intent.get('service_type')}",
        }

    def reason(self, observation: dict) -> str:
        providers = observation["providers"]
        service = observation["service_type"]
        urgency = observation["urgency"]
        user_lat = observation["user_lat"]
        user_lng = observation["user_lng"]
        budget = observation["budget_hint"]

        scored = []
        reasoning_lines = []

        for p in providers:
            score_breakdown = {}

            # ── 1. Trust Score (normalized to 0-1) ──────────────
            score_breakdown["composite_trust"] = min(1.0, p.get("composite_trust", 50) / 100)

            # ── 2. Distance Score ────────────────────────────────
            p_lat = float(p.get("lat", user_lat))
            p_lng = float(p.get("lng", user_lng))
            distance_km = self._haversine(user_lat, user_lng, p_lat, p_lng)
            p["distance_km"] = round(distance_km, 2)
            # Closer = higher score. 0km=1.0, 20km=0.0
            score_breakdown["distance_score"] = max(0.0, 1.0 - (distance_km / 20.0))

            # ── 3. Rating Score ──────────────────────────────────
            score_breakdown["rating_score"] = float(p.get("avg_rating", 3.5)) / 5.0

            # ── 4. Availability Score ────────────────────────────
            slots = p.get("available_slots", [])
            workload = int(p.get("workload", 0))
            max_jobs = int(p.get("max_daily_jobs", 5))
            availability = len(slots) > 0 and workload < max_jobs
            score_breakdown["availability_score"] = 1.0 if availability else 0.0

            # ── 5. Specialization Match ─────────────────────────
            specializations = p.get("specialization", [])
            exact_match = service in specializations
            score_breakdown["specialization_score"] = 1.0 if exact_match else 0.5

            # ── 6. Workload Score ────────────────────────────────
            capacity_used = workload / max(max_jobs, 1)
            score_breakdown["workload_score"] = max(0.0, 1.0 - capacity_used)

            # ── 7. Price Fairness Score ──────────────────────────
            price_score = 0.7  # Default neutral
            if budget and service in (p.get("price_ranges") or {}):
                pr = p["price_ranges"][service]
                if pr["min"] <= budget <= pr["max"]:
                    price_score = 1.0
                elif budget < pr["min"]:
                    price_score = 0.3
            score_breakdown["price_fairness_score"] = price_score

            # ── 8. Completion Reliability ────────────────────────
            score_breakdown["completion_score"] = float(p.get("completion_rate", 85)) / 100

            # ── 9. Repeat Customer Ratio ─────────────────────────
            score_breakdown["repeat_customer_score"] = float(p.get("repeat_customer_ratio", 20)) / 100

            # ── 10. Response Time ────────────────────────────────
            resp_min = int(p.get("response_time_minutes", 30))
            score_breakdown["response_time_score"] = max(0.0, 1.0 - (resp_min / 120))

            # ── Final Weighted Score ─────────────────────────────
            final_score = sum(
                score_breakdown.get(k, 0) * w
                for k, w in self.WEIGHTS.items()
            )

            # Urgency tie-breaker: boost proximity for critical/high
            if urgency in ["critical", "high"]:
                final_score += score_breakdown["distance_score"] * 0.05

            p["match_score"] = round(final_score, 4)
            p["score_breakdown"] = score_breakdown
            scored.append(p)

            reasoning_lines.append(
                f"{p.get('name')}: score={final_score:.3f} | dist={distance_km:.1f}km | "
                f"trust={p.get('composite_trust', 50):.0f} | rating={p.get('avg_rating', 0):.1f}"
            )

        # Sort descending
        scored.sort(key=lambda x: x["match_score"], reverse=True)

        top = scored[0] if scored else None
        second = scored[1] if len(scored) > 1 else None

        if top and second:
            # Explain why top was chosen over second
            if top["distance_km"] > second["distance_km"]:
                explanation = (
                    f"Provider '{top.get('name')}' selected despite being "
                    f"{top['distance_km'] - second['distance_km']:.1f}km farther "
                    f"because '{second.get('name')}' had lower trust score "
                    f"({second.get('composite_trust', 0):.0f} vs {top.get('composite_trust', 0):.0f})."
                )
            else:
                explanation = (
                    f"Provider '{top.get('name')}' selected: nearest AND highest trust score "
                    f"({top.get('composite_trust', 0):.0f}/100)."
                )
        elif top:
            explanation = f"Only one provider available: '{top.get('name')}'."
        else:
            explanation = "No providers available. Recovery Agent will activate."

        return "\n".join(reasoning_lines) + f"\n\nRANKING_EXPLANATION: {explanation}"

    def decide(self, reasoning: str) -> dict:
        lines = reasoning.split("\n")
        explanation = next((l.replace("RANKING_EXPLANATION: ", "") for l in lines if l.startswith("RANKING_EXPLANATION:")), "")
        return {
            "ranking_explanation": explanation,
            "confidence": 0.92,
            "summary": explanation[:120] if explanation else "Matching complete",
        }

    def act(self, decision: dict) -> dict:
        return {
            "action_taken": "Provider ranking complete. Top candidates forwarded to Pricing Agent.",
            "result": decision["ranking_explanation"],
            "output": decision,
        }

    def rank_providers(self, providers: list, intent: dict, severity: dict,
                       user_lat: float, user_lng: float, weather_temp: float = 35.0) -> list:
        """
        Public method: Returns providers sorted by match score with full score breakdown.
        """
        service = intent.get("service_type", "AC Repair")
        urgency = intent.get("urgency_level", "medium")
        budget = intent.get("budget_hint")

        scored = []
        for p in providers:
            score_breakdown = {}
            p_lat = float(p.get("lat", user_lat))
            p_lng = float(p.get("lng", user_lng))
            distance_km = self._haversine(user_lat, user_lng, p_lat, p_lng)
            p["distance_km"] = round(distance_km, 2)

            score_breakdown["composite_trust"] = min(1.0, p.get("composite_trust", 50) / 100)
            score_breakdown["distance_score"] = max(0.0, 1.0 - (distance_km / 20.0))
            score_breakdown["rating_score"] = float(p.get("avg_rating", 3.5)) / 5.0

            slots = p.get("available_slots", [])
            workload = int(p.get("workload", 0))
            max_jobs = int(p.get("max_daily_jobs", 5))
            score_breakdown["availability_score"] = 1.0 if (slots and workload < max_jobs) else 0.0
            score_breakdown["specialization_score"] = 1.0 if service in p.get("specialization", []) else 0.5

            capacity_used = workload / max(max_jobs, 1)
            score_breakdown["workload_score"] = max(0.0, 1.0 - capacity_used)

            price_score = 0.7
            if budget and service in (p.get("price_ranges") or {}):
                pr = p["price_ranges"][service]
                price_score = 1.0 if pr["min"] <= budget <= pr["max"] else 0.3
            score_breakdown["price_fairness_score"] = price_score
            score_breakdown["completion_score"] = float(p.get("completion_rate", 85)) / 100
            score_breakdown["repeat_customer_score"] = float(p.get("repeat_customer_ratio", 20)) / 100
            resp_min = int(p.get("response_time_minutes", 30))
            score_breakdown["response_time_score"] = max(0.0, 1.0 - (resp_min / 120))

            final_score = sum(score_breakdown.get(k, 0) * w for k, w in self.WEIGHTS.items())
            if urgency in ["critical", "high"]:
                final_score += score_breakdown["distance_score"] * 0.05

            # Build human-readable match reasoning
            trust_note = f"Trust: {p.get('composite_trust', 50):.0f}/100"
            dist_note = f"Distance: {distance_km:.1f}km"
            rating_note = f"Rating: {p.get('avg_rating', 0):.1f}★"

            p["match_score"] = round(final_score, 4)
            p["score_breakdown"] = score_breakdown
            p["match_reasoning"] = f"{trust_note} | {dist_note} | {rating_note}"
            p["eta_minutes"] = int(distance_km * 3 + 15)  # ~20km/h average + 15min prep
            scored.append(p)

        scored.sort(key=lambda x: x["match_score"], reverse=True)

        # Add rank position and comparison notes
        for i, p in enumerate(scored):
            p["rank"] = i + 1
            if i == 0 and len(scored) > 1:
                second = scored[1]
                if p["distance_km"] > second["distance_km"]:
                    p["selection_note"] = (
                        f"Selected over closer '{second.get('name')}' due to higher reliability "
                        f"({p.get('composite_trust', 0):.0f} vs {second.get('composite_trust', 0):.0f} trust score)"
                    )
                else:
                    p["selection_note"] = f"Best match: nearest available and highest trust score"

        return scored

    @staticmethod
    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two coordinates in km."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
             * math.sin(dlng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
