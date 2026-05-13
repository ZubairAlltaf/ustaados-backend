"""
UstaadOS — Pricing Agent
Generates deterministic, explainable dynamic pricing.
Prices are NEVER random — every rupee has a reason.
"""
from agents.base_agent import BaseAgent
from config import (
    BASE_PRICES, INSPECTION_FEES, TRAVEL_COST_PER_KM,
    URGENCY_FEES, HEATWAVE_SURGES
)


class PricingAgent(BaseAgent):
    name = "PricingAgent"

    COMPLEXITY_MULTIPLIERS = {
        "low": 1.0,
        "medium": 1.2,
        "high": 1.5,
        "critical": 1.8,
    }

    MARKET_DEMAND_FACTORS = {
        "low": 0.95,
        "normal": 1.0,
        "high": 1.10,
        "surge": 1.20,
    }

    LOYALTY_DISCOUNTS = {
        0: 0,
        5: 100,
        10: 200,
        25: 350,
        50: 500,
    }

    def observe(self, inputs: dict) -> dict:
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        provider = inputs.get("selected_provider", {})
        weather_temp = inputs.get("weather_temp", 35.0)
        user_loyalty_points = inputs.get("user_loyalty_points", 0)
        distance_km = provider.get("distance_km", 5.0)

        service = intent.get("service_type", "AC Repair")
        urgency = intent.get("urgency_level", "medium")
        complexity = severity.get("complexity", "medium")
        severity_score = severity.get("severity_score", 2.5)

        return {
            "service": service,
            "urgency": urgency,
            "complexity": complexity,
            "severity_score": severity_score,
            "weather_temp": weather_temp,
            "distance_km": distance_km,
            "user_loyalty_points": user_loyalty_points,
            "provider_price_range": provider.get("price_ranges", {}).get(service, {}),
            "summary": f"Pricing {service} | Urgency: {urgency} | Complexity: {complexity} | "
                       f"Temp: {weather_temp}°C | Distance: {distance_km:.1f}km",
        }

    def reason(self, observation: dict) -> str:
        service = observation["service"]
        urgency = observation["urgency"]
        complexity = observation["complexity"]
        severity_score = observation["severity_score"]
        weather_temp = observation["weather_temp"]
        distance_km = observation["distance_km"]
        loyalty_pts = observation["user_loyalty_points"]
        provider_range = observation["provider_price_range"]

        # ── Base Fee ──────────────────────────────────────────────────────
        base_fee = BASE_PRICES.get(service, 1500)

        # Adjust base to provider's range if available
        if provider_range:
            provider_min = provider_range.get("min", base_fee)
            provider_max = provider_range.get("max", base_fee * 4)
            base_fee = max(provider_min, base_fee)

        # ── Inspection Fee ────────────────────────────────────────────────
        inspection_fee = INSPECTION_FEES.get(service, 700)

        # ── Travel Cost ───────────────────────────────────────────────────
        per_km = TRAVEL_COST_PER_KM.get(service, 50)
        travel_cost = round(distance_km * per_km)

        # ── Urgency Fee ───────────────────────────────────────────────────
        urgency_fee = URGENCY_FEES.get(urgency, 0)

        # ── Heatwave Surge ────────────────────────────────────────────────
        if weather_temp < 38:
            surge_tier = "normal"
        elif weather_temp < 40:
            surge_tier = "warm"
        elif weather_temp < 43:
            surge_tier = "hot"
        elif weather_temp < 47:
            surge_tier = "extreme"
        else:
            surge_tier = "critical"

        heatwave_surge = HEATWAVE_SURGES.get(surge_tier, 0)

        # ── Complexity Multiplier ─────────────────────────────────────────
        complexity_multiplier = self.COMPLEXITY_MULTIPLIERS.get(complexity, 1.0)
        # Apply only to base fee, not flat fees
        base_with_complexity = round(base_fee * complexity_multiplier)
        complexity_fee = base_with_complexity - base_fee

        # ── Market Demand ─────────────────────────────────────────────────
        if weather_temp > 43 and urgency in ["high", "critical"]:
            demand_tier = "surge"
        elif weather_temp > 38 or urgency == "high":
            demand_tier = "high"
        else:
            demand_tier = "normal"

        demand_factor = self.MARKET_DEMAND_FACTORS.get(demand_tier, 1.0)

        # ── Loyalty Discount ──────────────────────────────────────────────
        loyalty_discount = 0
        for threshold in sorted(self.LOYALTY_DISCOUNTS.keys(), reverse=True):
            if loyalty_pts >= threshold:
                loyalty_discount = self.LOYALTY_DISCOUNTS[threshold]
                break

        # ── Final Calculation ─────────────────────────────────────────────
        subtotal = (base_fee + inspection_fee + travel_cost +
                    urgency_fee + heatwave_surge + complexity_fee)
        total_before_discount = round(subtotal * demand_factor)
        final_price = max(0, total_before_discount - loyalty_discount)

        breakdown = {
            "base_service_fee": base_fee,
            "inspection_fee": inspection_fee,
            "travel_cost": travel_cost,
            "urgency_fee": urgency_fee,
            "heatwave_surge": heatwave_surge,
            "heatwave_tier": surge_tier,
            "complexity_fee": complexity_fee,
            "complexity_multiplier": complexity_multiplier,
            "demand_factor": demand_factor,
            "demand_tier": demand_tier,
            "loyalty_discount": loyalty_discount,
            "subtotal": subtotal,
            "total_before_discount": total_before_discount,
            "final_price": final_price,
            "currency": "PKR",
        }

        reasoning_parts = [
            f"Base Service Fee: PKR {base_fee:,}",
            f"Inspection Fee: PKR {inspection_fee:,}",
            f"Travel Cost: PKR {travel_cost:,} ({distance_km:.1f}km × {per_km}/km)",
            f"Urgency Fee ({urgency}): PKR {urgency_fee:,}",
        ]
        if heatwave_surge > 0:
            reasoning_parts.append(
                f"Heatwave Surge ({surge_tier}, {weather_temp}°C): PKR {heatwave_surge:,}"
            )
        if complexity_fee > 0:
            reasoning_parts.append(
                f"Complexity Fee ({complexity}, ×{complexity_multiplier}): PKR {complexity_fee:,}"
            )
        if demand_factor != 1.0:
            reasoning_parts.append(f"Market Demand ({demand_tier}, ×{demand_factor}): applied to subtotal")
        if loyalty_discount > 0:
            reasoning_parts.append(f"Loyalty Discount: -PKR {loyalty_discount:,}")
        reasoning_parts.append(f"FINAL PRICE: PKR {final_price:,}")

        return "\n".join(reasoning_parts) + f"\n__BREAKDOWN_JSON__:{str(breakdown)}"

    def decide(self, reasoning: str) -> dict:
        # Extract breakdown JSON from reasoning string
        if "__BREAKDOWN_JSON__:" in reasoning:
            parts = reasoning.split("__BREAKDOWN_JSON__:")
            reasoning_text = parts[0].strip()
            try:
                breakdown = eval(parts[1].strip())  # safe dict literal
            except Exception:
                breakdown = {}
        else:
            reasoning_text = reasoning
            breakdown = {}

        final_price = breakdown.get("final_price", 2000)

        return {
            "final_price": final_price,
            "breakdown": breakdown,
            "reasoning_text": reasoning_text,
            "confidence": 1.0,  # Deterministic — always 100% confident
            "summary": f"Final Price: PKR {final_price:,} | "
                       f"Heatwave: {breakdown.get('heatwave_tier', 'normal')} | "
                       f"Demand: {breakdown.get('demand_tier', 'normal')}",
        }

    def act(self, decision: dict) -> dict:
        return {
            "action_taken": f"Price quote generated: PKR {decision['final_price']:,}",
            "result": f"Transparent quote ready. PKR {decision['final_price']:,} "
                      f"(breakdown: {len(decision['breakdown'])} factors applied)",
            "output": decision,
        }

    def calculate_price(self, intent: dict, severity: dict, provider: dict,
                        weather_temp: float, user_loyalty_points: int = 0) -> dict:
        """Public method: returns full price breakdown dict."""
        inputs = {
            "intent": intent,
            "severity": severity,
            "selected_provider": provider,
            "weather_temp": weather_temp,
            "user_loyalty_points": user_loyalty_points,
        }
        observation = self.observe(inputs)
        reasoning = self.reason(observation)
        decision = self.decide(reasoning)
        return decision
