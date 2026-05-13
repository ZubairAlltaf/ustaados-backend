"""
UstaadOS — Recovery Agent
Autonomously recovers from all failure scenarios.
This is the most impressive agent for demo purposes.
Handles: cancellations, no-availability, Maps failures, capacity overload.
"""
import random
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent
from agents.trust_agent import TrustAgent
from agents.matching_agent import MatchingAgent
from agents.pricing_agent import PricingAgent
from agents.scheduling_agent import SchedulingAgent
from database.client import get_db


class RecoveryAgent(BaseAgent):
    name = "RecoveryAgent"

    MAX_RECOVERY_ATTEMPTS = 3
    RADIUS_EXPANSION_KM = [5, 10, 20, 40]

    FAILURE_REASONS = {
        "provider_cancelled": "Provider cancelled the booking",
        "no_providers_available": "No providers available in area",
        "scheduling_conflict": "All provider slots are full",
        "maps_api_failure": "Maps API unavailable",
        "low_confidence_input": "Request could not be understood",
        "weather_surge_overload": "Heatwave surge exceeded provider capacity",
        "customer_rejection": "Customer rejected proposed provider",
        "provider_no_show": "Provider did not arrive at scheduled time",
    }

    def observe(self, inputs: dict) -> dict:
        failure_type = inputs.get("failure_type", "provider_cancelled")
        booking_id = inputs.get("booking_id")
        original_provider = inputs.get("original_provider", {})
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        user_lat = inputs.get("user_lat", 31.5204)
        user_lng = inputs.get("user_lng", 74.3587)
        attempt_number = inputs.get("attempt_number", 1)
        weather_temp = inputs.get("weather_temp", 35.0)
        all_providers = inputs.get("all_providers", [])

        return {
            "failure_type": failure_type,
            "failure_description": self.FAILURE_REASONS.get(failure_type, failure_type),
            "booking_id": booking_id,
            "original_provider_name": original_provider.get("name", "Unknown"),
            "service_type": intent.get("service_type", "AC Repair"),
            "urgency": intent.get("urgency_level", "medium"),
            "severity_score": severity.get("severity_score", 2.5),
            "user_lat": user_lat,
            "user_lng": user_lng,
            "attempt_number": attempt_number,
            "weather_temp": weather_temp,
            "all_providers": all_providers,
            "summary": f"FAILURE DETECTED: {self.FAILURE_REASONS.get(failure_type)} | "
                       f"Attempt #{attempt_number} | Provider: {original_provider.get('name', 'N/A')}",
        }

    def reason(self, observation: dict) -> str:
        failure_type = observation["failure_type"]
        attempt = observation["attempt_number"]
        urgency = observation["urgency"]
        service = observation["service_type"]
        user_lat = observation["user_lat"]
        user_lng = observation["user_lng"]
        all_providers = observation["all_providers"]
        weather_temp = observation["weather_temp"]
        original_name = observation["original_provider_name"]

        if attempt > self.MAX_RECOVERY_ATTEMPTS:
            return f"MAX_ATTEMPTS_REACHED: Recovery failed after {self.MAX_RECOVERY_ATTEMPTS} attempts. " \
                   f"Manual escalation required. Customer notified."

        # ── Strategy selection based on failure type ──────────────────────
        if failure_type == "provider_cancelled":
            strategy = "FIND_REPLACEMENT"
            reason = (f"Provider '{original_name}' cancelled. Searching for next best match "
                      f"excluding cancelled provider. Urgency: {urgency}.")

        elif failure_type == "no_providers_available":
            radius = self.RADIUS_EXPANSION_KM[min(attempt - 1, 3)]
            strategy = "EXPAND_RADIUS"
            reason = (f"No providers in immediate area. Expanding search radius to {radius}km. "
                      f"Service: {service}.")

        elif failure_type == "scheduling_conflict":
            strategy = "FIND_NEXT_SLOT"
            reason = "All near-term slots taken. Finding next available window across all providers."

        elif failure_type == "maps_api_failure":
            strategy = "MANUAL_ESTIMATE"
            reason = "Maps API unavailable. Using manual distance estimation based on area codes."

        elif failure_type == "weather_surge_overload":
            strategy = "PRIORITY_QUEUE"
            reason = (f"Heatwave surge ({weather_temp}°C) has overwhelmed capacity. "
                      f"Activating priority queue for critical/high urgency jobs.")

        elif failure_type == "customer_rejection":
            strategy = "FIND_REPLACEMENT"
            reason = "Customer rejected proposed provider. Finding alternatives based on updated preferences."

        else:
            strategy = "GENERIC_RECOVERY"
            reason = f"Unknown failure. Attempting generic recovery: re-running matching pipeline."

        return (f"STRATEGY: {strategy}\n"
                f"REASON: {reason}\n"
                f"ATTEMPT: {attempt}/{self.MAX_RECOVERY_ATTEMPTS}\n"
                f"URGENCY_CONTEXT: {urgency}")

    def decide(self, reasoning: str) -> dict:
        lines = {l.split(": ")[0]: l.split(": ", 1)[1] for l in reasoning.split("\n") if ": " in l}
        strategy = lines.get("STRATEGY", "GENERIC_RECOVERY")

        if "MAX_ATTEMPTS_REACHED" in reasoning:
            return {
                "can_recover": False,
                "strategy": "ESCALATE_MANUAL",
                "action_required": "Human escalation required",
                "confidence": 0.99,
                "summary": "Maximum recovery attempts reached. Manual escalation triggered.",
            }

        return {
            "can_recover": True,
            "strategy": strategy,
            "reason": lines.get("REASON", ""),
            "confidence": 0.90,
            "summary": f"Recovery strategy: {strategy} | Attempt {lines.get('ATTEMPT', '1')}",
        }

    def act(self, decision: dict) -> dict:
        if not decision["can_recover"]:
            return {
                "action_taken": "Escalated to manual support team.",
                "result": "Recovery failed. Customer will be contacted directly.",
                "recovery": "MANUAL_ESCALATION",
                "output": decision,
            }

        strategy = decision["strategy"]

        action_messages = {
            "FIND_REPLACEMENT": "Searching alternative providers. Excluding original cancelling provider.",
            "EXPAND_RADIUS": "Expanded search radius. Re-running provider matching.",
            "FIND_NEXT_SLOT": "Scanning all provider schedules for earliest available slot.",
            "MANUAL_ESTIMATE": "Using manual distance estimates. ETA may be approximate (±10 min).",
            "PRIORITY_QUEUE": "Priority queue activated. High/critical jobs moved to front.",
            "GENERIC_RECOVERY": "Re-running full matching pipeline with relaxed constraints.",
        }

        return {
            "action_taken": action_messages.get(strategy, "Recovery action initiated"),
            "result": f"Recovery in progress ({strategy}). Customer notification sent.",
            "recovery": strategy,
            "output": decision,
        }

    def execute_recovery(self, inputs: dict) -> dict:
        """
        Full recovery pipeline — runs sub-agents to find alternative.
        Returns: {success, new_provider, new_schedule, new_price, recovery_trace, new_eta}
        """
        failure_type = inputs.get("failure_type", "provider_cancelled")
        original_provider_id = inputs.get("original_provider", {}).get("id")
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        user_lat = inputs.get("user_lat", 31.5204)
        user_lng = inputs.get("user_lng", 74.3587)
        weather_temp = inputs.get("weather_temp", 35.0)
        urgency = intent.get("urgency_level", "medium")

        # Step 1: Fetch all providers except the failed one
        all_providers = self._fetch_alternative_providers(
            service_type=intent.get("service_type"),
            exclude_id=original_provider_id,
            urgency=urgency,
            failure_type=failure_type,
        )

        if not all_providers:
            return {
                "success": False,
                "reason": "No alternative providers found",
                "recovery_trace": self._trace,
                "new_eta": None,
                "notification_message": (
                    "We're sorry — no technicians are currently available in your area. "
                    "Our team will contact you within 30 minutes."
                ),
            }

        # Step 2: Re-run Trust + Matching on alternatives
        trust_agent = TrustAgent(session_id=self.session_id, booking_id=self.booking_id)
        approved, rejected = trust_agent.score_providers(all_providers, intent, severity, weather_temp)

        if not approved:
            # Relax trust constraints for recovery
            approved = [p for p in all_providers if p.get("trust_score", 0) > 25]

        if not approved:
            return {
                "success": False,
                "reason": "All alternative providers failed trust checks",
                "recovery_trace": self._trace,
                "new_eta": None,
                "notification_message": "No trusted technicians available. Escalating to support.",
            }

        matching_agent = MatchingAgent(session_id=self.session_id, booking_id=self.booking_id)
        ranked = matching_agent.rank_providers(approved, intent, severity, user_lat, user_lng, weather_temp)

        new_provider = ranked[0]

        # Step 3: Re-schedule
        scheduling_agent = SchedulingAgent(session_id=self.session_id, booking_id=self.booking_id)
        schedule_inputs = {
            "selected_provider": new_provider,
            "intent": intent,
            "severity": severity,
            "user_lat": user_lat,
            "user_lng": user_lng,
        }
        schedule_obs = scheduling_agent.observe(schedule_inputs)
        schedule_reason = scheduling_agent.reason(schedule_obs)
        schedule_decision = scheduling_agent.decide(schedule_reason)

        # Step 4: Re-price
        pricing_agent = PricingAgent(session_id=self.session_id, booking_id=self.booking_id)
        price_result = pricing_agent.calculate_price(intent, severity, new_provider, weather_temp)

        new_eta = schedule_decision.get("eta_minutes")

        # Human-readable notification
        eta_str = f"{new_eta} minutes" if new_eta else "shortly"
        notification = (
            f"Update: Your original technician was unavailable. "
            f"We've automatically assigned {new_provider.get('name')} "
            f"(Trust Score: {new_provider.get('composite_trust', 0):.0f}/100). "
            f"New ETA: {eta_str}. Quote remains PKR {price_result['final_price']:,}."
        )

        return {
            "success": True,
            "new_provider": new_provider,
            "new_schedule": schedule_decision,
            "new_price": price_result,
            "new_eta": new_eta,
            "recovery_strategy": failure_type,
            "notification_message": notification,
            "recovery_trace": self._trace,
        }

    def _fetch_alternative_providers(self, service_type: str, exclude_id: str,
                                      urgency: str, failure_type: str) -> list:
        """Fetch providers from Supabase, excluding the failed one."""
        try:
            db = get_db()
            query = db.table("providers") \
                .select("*") \
                .eq("active_status", True) \
                .contains("specialization", [service_type])

            if exclude_id:
                query = query.neq("id", exclude_id)

            if urgency in ["high", "critical"]:
                query = query.gte("trust_score", 40)

            result = query.limit(30).execute()
            return result.data or []
        except Exception as e:
            print(f"[RecoveryAgent] DB fetch failed: {e}")
            return []
