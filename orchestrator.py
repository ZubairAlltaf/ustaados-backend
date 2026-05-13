"""
UstaadOS — Orchestrator
The central brain that sequences all 8 agents for each request.
Produces a complete trace timeline for the UI.
"""
import uuid
import httpx
from datetime import datetime
from typing import Optional

from agents.intent_agent import IntentAgent
from agents.severity_agent import SeverityAgent
from agents.trust_agent import TrustAgent
from agents.matching_agent import MatchingAgent
from agents.pricing_agent import PricingAgent
from agents.scheduling_agent import SchedulingAgent
from agents.recovery_agent import RecoveryAgent
from agents.dispute_agent import DisputeAgent
from database.client import get_db
from config import (
    OPENWEATHER_API_KEY, OPENWEATHER_CITY,
    GOOGLE_MAPS_API_KEY
)


class UstaadOrchestrator:
    """
    Orchestrates the full UstaadOS agent pipeline.
    Sequence:
      Intent → Severity → Trust → Matching → Pricing → Scheduling
                                                             ↓ (on failure)
                                                       Recovery
    """

    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.traces: list[dict] = []

    # ─── Main Orchestration ───────────────────────────────────────────────

    async def process_request(self, request_data: dict) -> dict:
        """
        Full pipeline for a new service request.
        Returns booking result with full trace timeline.
        """
        user_lat = request_data.get("lat", 31.5204)
        user_lng = request_data.get("lng", 74.3587)
        user_id = request_data.get("user_id")
        loyalty_points = request_data.get("loyalty_points", 0)

        # ── Step 0: Get Weather ──────────────────────────────────────────
        weather_temp = await self._get_weather_temp(lat=user_lat, lng=user_lng)

        # ── Step 1: Intent Agent ─────────────────────────────────────────
        intent_agent = IntentAgent(session_id=self.session_id)
        intent_trace = intent_agent.run({
            "text": request_data.get("text", ""),
            "voice_transcript": request_data.get("voice_transcript", ""),
            "location": {"lat": user_lat, "lng": user_lng},
        })
        self.traces.append(intent_trace)
        intent = intent_trace["metadata"]["decision_detail"]

        if intent.get("needs_clarification"):
            return {
                "status": "needs_clarification",
                "question": intent["clarification_question"],
                "traces": self.traces,
                "session_id": self.session_id,
            }

        # ── Step 2: Severity Agent ───────────────────────────────────────
        severity_agent = SeverityAgent(session_id=self.session_id)
        severity_trace = severity_agent.run({
            "intent": intent,
            "weather_temp": weather_temp,
        })
        self.traces.append(severity_trace)
        severity = severity_trace["metadata"]["decision_detail"]

        # ── Step 3: Fetch Candidate Providers ────────────────────────────
        providers = await self._fetch_providers(
            service_type=intent.get("service_type"),
            urgency=intent.get("urgency_level"),
            user_lat=user_lat,
            user_lng=user_lng,
        )

        if not providers:
            # Trigger Recovery
            return await self._trigger_recovery(
                failure_type="no_providers_available",
                intent=intent,
                severity=severity,
                user_lat=user_lat,
                user_lng=user_lng,
                weather_temp=weather_temp,
            )

        # ── Step 4: Trust Agent ──────────────────────────────────────────
        trust_agent = TrustAgent(session_id=self.session_id)
        trust_trace = trust_agent.run({
            "providers": providers,
            "intent": intent,
            "severity": severity,
            "weather_temp": weather_temp,
        })
        self.traces.append(trust_trace)
        approved, rejected = trust_agent.score_providers(providers, intent, severity, weather_temp)

        if not approved:
            return await self._trigger_recovery(
                failure_type="no_providers_available",
                intent=intent,
                severity=severity,
                user_lat=user_lat,
                user_lng=user_lng,
                weather_temp=weather_temp,
                all_providers=providers,
            )

        # ── Step 5: Matching Agent ───────────────────────────────────────
        matching_agent = MatchingAgent(session_id=self.session_id)
        matching_trace = matching_agent.run({
            "trusted_providers": approved,
            "intent": intent,
            "severity": severity,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "weather_temp": weather_temp,
        })
        self.traces.append(matching_trace)
        ranked_providers = matching_agent.rank_providers(
            approved, intent, severity, user_lat, user_lng, weather_temp
        )
        selected_provider = ranked_providers[0]

        # ── Step 6: Pricing Agent ────────────────────────────────────────
        pricing_agent = PricingAgent(session_id=self.session_id)
        pricing_trace = pricing_agent.run({
            "intent": intent,
            "severity": severity,
            "selected_provider": selected_provider,
            "weather_temp": weather_temp,
            "user_loyalty_points": loyalty_points,
        })
        self.traces.append(pricing_trace)
        price_result = pricing_trace["metadata"]["decision_detail"]

        # ── Step 7: Scheduling Agent ─────────────────────────────────────
        scheduling_agent = SchedulingAgent(session_id=self.session_id)
        scheduling_trace = scheduling_agent.run({
            "selected_provider": selected_provider,
            "intent": intent,
            "severity": severity,
            "user_lat": user_lat,
            "user_lng": user_lng,
        })
        self.traces.append(scheduling_trace)
        schedule = scheduling_trace["metadata"]["decision_detail"]

        if not schedule.get("can_schedule"):
            return await self._trigger_recovery(
                failure_type="scheduling_conflict",
                intent=intent,
                severity=severity,
                user_lat=user_lat,
                user_lng=user_lng,
                weather_temp=weather_temp,
                original_provider=selected_provider,
            )

        # ── Step 8: Create Booking Record ────────────────────────────────
        booking = await self._create_booking(
            user_id=user_id,
            provider=selected_provider,
            intent=intent,
            severity=severity,
            price_result=price_result,
            schedule=schedule,
            weather_temp=weather_temp,
        )

        return {
            "status": "confirmed",
            "booking": booking,
            "selected_provider": self._safe_provider(selected_provider),
            "alternative_providers": [self._safe_provider(p) for p in ranked_providers[1:4]],
            "rejected_providers": [
                {
                    "name": p.get("name"),
                    "rejection_reasons": p.get("rejection_reasons", []),
                }
                for p in rejected[:3]
            ],
            "pricing": price_result,
            "schedule": schedule,
            "weather": {"temp": weather_temp, "is_heatwave": weather_temp > 40},
            "traces": self.traces,
            "session_id": self.session_id,
        }

    async def cancel_and_recover(self, booking_id: str, failure_type: str,
                                  reason: str, user_id: str | None = None) -> dict:
        """Handle booking cancellation and auto-recover."""
        db = get_db()

        # Fetch booking details
        try:
            booking_data = db.table("bookings").select("*").eq("id", booking_id).single().execute()
            booking = booking_data.data
        except Exception:
            return {"success": False, "reason": "Booking not found"}

        # Update booking status
        db.table("bookings").update({
            "status": "recovery_in_progress",
            "cancellation_reason": reason,
            "cancelled_by": "provider" if failure_type == "provider_cancelled" else "system",
            "recovery_attempts": booking.get("recovery_attempts", 0) + 1,
        }).eq("id", booking_id).execute()

        # Get original provider
        provider_data = {}
        if booking.get("provider_id"):
            try:
                prov = db.table("providers").select("*").eq("id", booking["provider_id"]).single().execute()
                provider_data = prov.data or {}
            except Exception:
                pass

        weather_temp = await self._get_weather_temp(
            lat=booking.get("user_lat", 31.5204),
            lng=booking.get("user_lng", 74.3587)
        )

        # Run Recovery Agent
        recovery_agent = RecoveryAgent(session_id=self.session_id, booking_id=booking_id)
        recovery_trace = recovery_agent.run({
            "failure_type": failure_type,
            "booking_id": booking_id,
            "original_provider": provider_data,
            "intent": {
                "service_type": booking.get("service_type"),
                "urgency_level": booking.get("urgency_level"),
            },
            "severity": {"severity_score": booking.get("severity_score", 2.5)},
            "user_lat": booking.get("user_lat", 31.5204),
            "user_lng": booking.get("user_lng", 74.3587),
            "attempt_number": booking.get("recovery_attempts", 1),
            "weather_temp": weather_temp,
        })
        self.traces.append(recovery_trace)

        result = recovery_agent.execute_recovery({
            "failure_type": failure_type,
            "original_provider": provider_data,
            "intent": {
                "service_type": booking.get("service_type"),
                "urgency_level": booking.get("urgency_level"),
            },
            "severity": {"severity_score": booking.get("severity_score", 2.5)},
            "user_lat": booking.get("user_lat", 31.5204),
            "user_lng": booking.get("user_lng", 74.3587),
            "weather_temp": weather_temp,
        })

        if result["success"]:
            # Update booking with new provider
            db.table("bookings").update({
                "status": "recovered",
                "provider_id": result["new_provider"]["id"],
                "original_provider_id": booking.get("provider_id"),
                "scheduled_time": result["new_schedule"].get("recommended_slot"),
                "price": result["new_price"].get("final_price"),
                "price_breakdown": result["new_price"].get("breakdown"),
            }).eq("id", booking_id).execute()

            # Send notification
            await self._create_notification(
                user_id=booking.get("user_id"),
                booking_id=booking_id,
                notif_type="recovery_success",
                title="Technician Replaced Successfully",
                body=result["notification_message"],
            )
        else:
            db.table("bookings").update({"status": "recovery_needed"}).eq("id", booking_id).execute()

        return {**result, "traces": self.traces, "session_id": self.session_id}

    async def resolve_dispute(self, dispute_data: dict) -> dict:
        """Process a post-service dispute."""
        dispute_agent = DisputeAgent(session_id=self.session_id)
        dispute_trace = dispute_agent.run(dispute_data)
        self.traces.append(dispute_trace)

        decision = dispute_trace["metadata"]["decision_detail"]

        # Persist dispute
        db = get_db()
        try:
            db.table("disputes").insert({
                "booking_id": dispute_data.get("booking_id"),
                "user_id": dispute_data.get("user_id"),
                "provider_id": dispute_data.get("provider_id"),
                "dispute_type": dispute_data.get("dispute_type"),
                "description": dispute_data.get("description"),
                "quoted_price": dispute_data.get("quoted_price"),
                "actual_charged": dispute_data.get("actual_charged"),
                "status": "investigating" if decision["verdict"] == "ESCALATE" else "resolved",
                "resolution": decision["verdict_reason"],
                "refund_amount": decision["recommended_refund_amount"],
                "ai_verdict": decision["verdict"],
                "ai_confidence": decision["confidence"],
                "resolved_at": datetime.utcnow().isoformat() if decision["verdict"] != "ESCALATE" else None,
            }).execute()
        except Exception as e:
            print(f"[Orchestrator] Dispute persist failed: {e}")

        return {
            "dispute_resolved": decision["verdict"] != "ESCALATE",
            "verdict": decision["verdict"],
            "verdict_reason": decision["verdict_reason"],
            "refund_amount": decision["recommended_refund_amount"],
            "provider_action": decision["provider_action"],
            "traces": self.traces,
        }

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _get_weather_temp(self, lat: float = None, lng: float = None) -> float:
        """Fetch current temperature from OpenWeather API using lat/lng or fallback city."""
        if not OPENWEATHER_API_KEY:
            return 38.0  # Fallback for dev

        try:
            if lat and lng:
                url = (f"https://api.openweathermap.org/data/2.5/weather"
                       f"?lat={lat}&lon={lng}&appid={OPENWEATHER_API_KEY}&units=metric")
            else:
                url = (f"https://api.openweathermap.org/data/2.5/weather"
                       f"?q={OPENWEATHER_CITY}&appid={OPENWEATHER_API_KEY}&units=metric")
                
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                data = resp.json()
                return float(data["main"]["temp"])
        except Exception:
            return 38.0  # Safe fallback

    async def _fetch_providers(self, service_type: str, urgency: str,
                                user_lat: float, user_lng: float) -> list:
        """Fetch candidate providers from Supabase."""
        try:
            db = get_db()
            query = (db.table("providers")
                     .select("*")
                     .eq("active_status", True)
                     .eq("city", "Lahore"))

            if urgency in ["high", "critical"]:
                query = query.gte("trust_score", 35)

            result = query.limit(50).execute()
            providers = result.data or []

            # Filter by specialization
            providers = [
                p for p in providers
                if service_type in (p.get("specialization") or [])
            ]
            return providers
        except Exception as e:
            print(f"[Orchestrator] Provider fetch failed: {e}")
            return []

    async def _trigger_recovery(self, failure_type: str, intent: dict, severity: dict,
                                 user_lat: float, user_lng: float, weather_temp: float,
                                 original_provider: dict = None,
                                 all_providers: list = None) -> dict:
        recovery_agent = RecoveryAgent(session_id=self.session_id)
        recovery_trace = recovery_agent.run({
            "failure_type": failure_type,
            "original_provider": original_provider or {},
            "intent": intent,
            "severity": severity,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "weather_temp": weather_temp,
            "all_providers": all_providers or [],
        })
        self.traces.append(recovery_trace)

        return {
            "status": "recovery_initiated",
            "failure_type": failure_type,
            "recovery_strategy": recovery_trace["recovery"],
            "traces": self.traces,
            "session_id": self.session_id,
        }

    async def _create_booking(self, user_id: str | None, provider: dict, intent: dict,
                               severity: dict, price_result: dict, schedule: dict,
                               weather_temp: float) -> dict:
        db = get_db()
        booking_data = {
            "provider_id": provider["id"],
            "service_type": intent.get("service_type"),
            "issue_type": intent.get("issue_description", "")[:100],
            "urgency_level": intent.get("urgency_level"),
            "severity_score": severity.get("severity_score"),
            "status": "confirmed",
            "scheduled_time": schedule.get("recommended_slot"),
            "estimated_duration_minutes": severity.get("estimated_duration_minutes", 60),
            "price": price_result.get("final_price"),
            "price_breakdown": price_result.get("breakdown", {}),
            "trust_snapshot": {
                "trust_score": provider.get("composite_trust"),
                "cancellation_rate": provider.get("cancellation_rate"),
                "avg_rating": provider.get("avg_rating"),
                "trust_verdict": provider.get("trust_verdict"),
            },
            "match_reasoning": provider.get("selection_note", ""),
            "is_heatwave_surge": weather_temp > 40,
            "weather_temp": weather_temp,
        }

        if user_id:
            booking_data["user_id"] = user_id

        try:
            result = db.table("bookings").insert(booking_data).execute()
            booking = result.data[0] if result.data else booking_data
            booking_id = booking.get("id")

            # Update booking_id on all traces
            if booking_id:
                for trace in self.traces:
                    trace["booking_id"] = booking_id

            return booking
        except Exception as e:
            print(f"[Orchestrator] Booking persist failed: {e}")
            return booking_data

    async def _create_notification(self, user_id: str | None, booking_id: str,
                                   notif_type: str, title: str, body: str) -> None:
        if not user_id:
            return
        try:
            db = get_db()
            db.table("notifications").insert({
                "user_id": user_id,
                "booking_id": booking_id,
                "type": notif_type,
                "title": title,
                "body": body,
            }).execute()
        except Exception:
            pass

    @staticmethod
    def _safe_provider(p: dict) -> dict:
        """Return provider dict without sensitive internal fields."""
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "area": p.get("area"),
            "distance_km": p.get("distance_km"),
            "eta_minutes": p.get("eta_minutes"),
            "avg_rating": p.get("avg_rating"),
            "trust_score": p.get("trust_score"),
            "composite_trust": p.get("composite_trust"),
            "trust_verdict": p.get("trust_verdict"),
            "match_score": p.get("match_score"),
            "match_reasoning": p.get("match_reasoning"),
            "selection_note": p.get("selection_note"),
            "rank": p.get("rank"),
            "specialization": p.get("specialization"),
            "price_ranges": p.get("price_ranges"),
            "available_slots": p.get("available_slots", [])[:3],
            "phone": p.get("phone"),
            "is_verified": p.get("is_verified"),
        }
