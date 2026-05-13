"""
UstaadOS — Scheduling Agent
Prevents overlaps, calculates travel buffers,
manages queues, and optimizes technician utilization.
"""
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent
from database.client import get_db


class SchedulingAgent(BaseAgent):
    name = "SchedulingAgent"

    BUFFER_MINUTES = 30  # Minimum gap between bookings
    TRAVEL_SPEED_KM_H = 20  # Lahore average traffic speed

    def observe(self, inputs: dict) -> dict:
        provider = inputs.get("selected_provider", {})
        intent = inputs.get("intent", {})
        severity = inputs.get("severity", {})
        user_lat = inputs.get("user_lat", 31.5204)
        user_lng = inputs.get("user_lng", 74.3587)

        time_pref = intent.get("time_preference", "Any")
        urgency = intent.get("urgency_level", "medium")
        est_duration = severity.get("estimated_duration_minutes", 60)
        distance_km = provider.get("distance_km", 5.0)

        return {
            "provider_id": provider.get("id"),
            "provider_name": provider.get("name"),
            "available_slots": provider.get("available_slots", []),
            "workload": provider.get("workload", 0),
            "max_daily_jobs": provider.get("max_daily_jobs", 5),
            "time_preference": time_pref,
            "urgency": urgency,
            "est_duration_minutes": est_duration,
            "distance_km": distance_km,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "summary": f"Scheduling for {provider.get('name')} | Pref: {time_pref} | "
                       f"Urgency: {urgency} | Workload: {provider.get('workload')}/{provider.get('max_daily_jobs')}",
        }

    def reason(self, observation: dict) -> str:
        provider_id = observation["provider_id"]
        provider_name = observation["provider_name"]
        time_pref = observation["time_preference"]
        urgency = observation["urgency"]
        est_duration = observation["est_duration_minutes"]
        distance_km = observation["distance_km"]
        workload = observation["workload"]
        max_jobs = observation["max_daily_jobs"]
        available_slots = observation["available_slots"]

        # ── Travel Time Calculation ───────────────────────────────────────
        travel_minutes = int((distance_km / self.TRAVEL_SPEED_KM_H) * 60) + 10
        total_slot_duration = est_duration + travel_minutes + self.BUFFER_MINUTES

        # ── Capacity Check ────────────────────────────────────────────────
        if workload >= max_jobs:
            return f"CAPACITY_EXCEEDED: Provider at max workload ({workload}/{max_jobs}). " \
                   f"Must waitlist or find alternative."

        # ── Check Existing Bookings for Conflicts ─────────────────────────
        conflict_slots = self._get_provider_schedule(provider_id)

        # ── Find Best Slot ────────────────────────────────────────────────
        now = datetime.utcnow()

        # ASAP/critical: find the very next available window
        if urgency == "critical" or time_pref in ["ASAP", "Today"]:
            candidate = now + timedelta(minutes=travel_minutes + 15)
        elif time_pref == "Tomorrow Morning":
            tomorrow = now + timedelta(days=1)
            candidate = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        elif time_pref == "Tomorrow Evening":
            tomorrow = now + timedelta(days=1)
            candidate = tomorrow.replace(hour=17, minute=0, second=0, microsecond=0)
        else:
            # Default: next morning slot
            candidate = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

        # Check for conflicts and adjust
        attempts = 0
        while attempts < 8:
            conflict = self._check_conflict(candidate, total_slot_duration, conflict_slots)
            if not conflict:
                break
            candidate += timedelta(minutes=total_slot_duration)
            attempts += 1

        if attempts >= 8:
            return f"SLOT_NOT_FOUND: No available slot in next 8 windows. Waitlisted."

        # Generate alternate slots
        alt1 = candidate + timedelta(hours=2)
        alt2 = candidate + timedelta(days=1)
        while self._check_conflict(alt1, total_slot_duration, conflict_slots):
            alt1 += timedelta(minutes=60)

        eta_from_now = int((candidate - now).total_seconds() / 60)

        result_lines = [
            f"SCHEDULED: {candidate.isoformat()}",
            f"ETA_MINUTES: {eta_from_now}",
            f"TRAVEL_TIME: {travel_minutes} minutes",
            f"DURATION: {est_duration} minutes",
            f"BUFFER: {self.BUFFER_MINUTES} minutes",
            f"ALT1: {alt1.isoformat()}",
            f"ALT2: {alt2.isoformat()}",
            f"CONFLICT_CHECK: {attempts} windows checked",
        ]
        return "\n".join(result_lines)

    def decide(self, reasoning: str) -> dict:
        if "CAPACITY_EXCEEDED" in reasoning:
            return {
                "can_schedule": False,
                "reason": "Provider at full capacity",
                "recommended_slot": None,
                "eta_minutes": None,
                "confidence": 0.99,
                "summary": "Cannot schedule — capacity exceeded. Trigger Recovery Agent.",
            }

        if "SLOT_NOT_FOUND" in reasoning:
            return {
                "can_schedule": False,
                "reason": "No available slots in scheduling window",
                "recommended_slot": None,
                "eta_minutes": None,
                "confidence": 0.99,
                "summary": "Cannot schedule — all slots full. Trigger Recovery Agent.",
            }

        lines = {l.split(": ")[0]: l.split(": ", 1)[1] for l in reasoning.split("\n") if ": " in l}

        return {
            "can_schedule": True,
            "recommended_slot": lines.get("SCHEDULED"),
            "eta_minutes": int(lines.get("ETA_MINUTES", "30")),
            "travel_time_minutes": int(lines.get("TRAVEL_TIME", "15")),
            "duration_minutes": int(lines.get("DURATION", "60")),
            "alternate_slots": [lines.get("ALT1"), lines.get("ALT2")],
            "confidence": 0.95,
            "summary": f"Slot: {lines.get('SCHEDULED', 'TBD')} | ETA: {lines.get('ETA_MINUTES')} min",
        }

    def act(self, decision: dict) -> dict:
        if not decision["can_schedule"]:
            return {
                "action_taken": "Scheduling failed. Notifying Recovery Agent.",
                "result": decision["reason"],
                "recovery": "Recovery Agent will find alternative provider or slot.",
                "output": decision,
            }

        return {
            "action_taken": f"Slot reserved: {decision['recommended_slot']}",
            "result": f"Booking confirmed for slot {decision['recommended_slot']}. "
                      f"ETA: {decision['eta_minutes']} minutes.",
            "output": decision,
        }

    def _get_provider_schedule(self, provider_id: str) -> list:
        """Fetch existing scheduled slots for a provider."""
        try:
            db = get_db()
            result = db.table("provider_schedules") \
                .select("start_time,end_time") \
                .eq("provider_id", provider_id) \
                .eq("status", "booked") \
                .execute()
            return result.data or []
        except Exception:
            return []

    def _check_conflict(self, start: datetime, duration_minutes: int, booked_slots: list) -> bool:
        """Check if a proposed slot conflicts with existing bookings."""
        end = start + timedelta(minutes=duration_minutes)
        for slot in booked_slots:
            try:
                s_start = datetime.fromisoformat(slot["start_time"])
                s_end = datetime.fromisoformat(slot["end_time"])
                # Add buffer on both sides
                buffered_start = s_start - timedelta(minutes=self.BUFFER_MINUTES)
                buffered_end = s_end + timedelta(minutes=self.BUFFER_MINUTES)
                if start < buffered_end and end > buffered_start:
                    return True
            except Exception:
                continue
        return False
