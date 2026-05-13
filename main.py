"""
UstaadOS — FastAPI Backend
Full production API with auth, all agent routes, realtime, and stress tests.
"""
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

from orchestrator import UstaadOrchestrator
from database.client import get_db
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, APP_VERSION

# ─── App Setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="UstaadOS API",
    description="Pakistan's Agentic Technician Orchestration Platform",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ───────────────────────────────────────────────────────

class ServiceRequestBody(BaseModel):
    text: str = Field(..., min_length=3, description="User request in Roman Urdu/Urdu/English")
    voice_transcript: Optional[str] = None
    lat: float = Field(31.5204, ge=20.0, le=40.0)
    lng: float = Field(74.3587, ge=60.0, le=80.0)
    user_id: Optional[str] = None
    loyalty_points: int = Field(0, ge=0)

class CancelBookingBody(BaseModel):
    failure_type: str = Field("provider_cancelled")
    reason: str = Field("Provider unavailable")

class DisputeBody(BaseModel):
    booking_id: str
    user_id: Optional[str] = None
    provider_id: Optional[str] = None
    dispute_type: str
    description: str
    quoted_price: float = 0
    actual_charged: float = 0

class ReviewBody(BaseModel):
    booking_id: str
    provider_id: str
    user_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None
    complaint_type: Optional[str] = None

class UpdateBookingStatus(BaseModel):
    status: str

class StressTestBody(BaseModel):
    scenario: str
    lat: float = 31.5204
    lng: float = 74.3587

# ─── Auth Dependency ────────────────────────────────────────────────────────

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Extract user from Supabase JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    try:
        db = get_db()
        user = db.auth.get_user(token)
        return user.user if user else None
    except Exception:
        return None

async def require_auth(user: Optional[dict] = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

# ─── Root & Health ─────────────────────────────────────────────────────────

@app.get("/", tags=["System"])
async def root():
    return {
        "system": "UstaadOS",
        "tagline": "Autonomous coordination for Pakistan's technician economy.",
        "version": APP_VERSION,
        "status": "operational",
        "agents": [
            "IntentAgent", "SeverityAgent", "TrustAgent", "MatchingAgent",
            "PricingAgent", "SchedulingAgent", "RecoveryAgent", "DisputeAgent"
        ],
    }

@app.get("/health", tags=["System"])
async def health():
    try:
        db = get_db()
        db.table("providers").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"
    return {"status": "ok", "database": db_status, "version": APP_VERSION}

# ─── Core Orchestration ─────────────────────────────────────────────────────

@app.post("/api/v1/request", tags=["Orchestration"])
async def process_service_request(body: ServiceRequestBody):
    """
    Full orchestration pipeline:
    Intent → Severity → Trust → Match → Price → Schedule → Booking
    """
    orchestrator = UstaadOrchestrator()
    try:
        result = await orchestrator.process_request(body.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestration failed: {str(e)}")

# ─── Providers ──────────────────────────────────────────────────────────────

@app.get("/api/v1/providers", tags=["Providers"])
async def list_providers(
    city: str = "Lahore",
    service: Optional[str] = None,
    min_trust: float = 0,
    limit: int = 20,
    offset: int = 0,
):
    db = get_db()
    query = db.table("providers").select("*").eq("city", city).eq("active_status", True)

    if min_trust > 0:
        query = query.gte("trust_score", min_trust)

    query = query.order("trust_score", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    providers = result.data or []

    if service:
        providers = [p for p in providers if service in (p.get("specialization") or [])]

    return {"providers": providers, "total": len(providers), "city": city}

@app.get("/api/v1/providers/{provider_id}", tags=["Providers"])
async def get_provider(provider_id: str):
    db = get_db()
    try:
        result = db.table("providers").select("*").eq("id", provider_id).single().execute()
        provider = result.data
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        # Fetch recent reviews
        reviews = db.table("reviews").select("*") \
            .eq("provider_id", provider_id) \
            .order("created_at", desc=True).limit(10).execute()

        return {
            "provider": provider,
            "recent_reviews": reviews.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Bookings ───────────────────────────────────────────────────────────────

@app.get("/api/v1/bookings/{booking_id}", tags=["Bookings"])
async def get_booking(booking_id: str):
    db = get_db()
    try:
        result = db.table("bookings").select("*").eq("id", booking_id).single().execute()
        booking = result.data
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Fetch associated traces
        traces = db.table("traces").select("*") \
            .eq("booking_id", booking_id) \
            .order("timestamp").execute()

        # Fetch provider
        provider = {}
        if booking.get("provider_id"):
            p = db.table("providers").select(
                "id,name,phone,area,avg_rating,trust_score,lat,lng"
            ).eq("id", booking["provider_id"]).single().execute()
            provider = p.data or {}

        return {
            "booking": booking,
            "provider": provider,
            "traces": traces.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/bookings", tags=["Bookings"])
async def list_user_bookings(user_id: str, limit: int = 20):
    db = get_db()
    result = db.table("bookings").select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(limit).execute()
    return {"bookings": result.data or []}

@app.put("/api/v1/bookings/{booking_id}/status", tags=["Bookings"])
async def update_booking_status(booking_id: str, body: UpdateBookingStatus):
    db = get_db()
    try:
        result = db.table("bookings").update({"status": body.status}).eq("id", booking_id).execute()
        return {"success": True, "booking_id": booking_id, "new_status": body.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/bookings/{booking_id}/cancel", tags=["Bookings"])
async def cancel_booking(booking_id: str, body: CancelBookingBody):
    """Cancel a booking and automatically trigger recovery."""
    orchestrator = UstaadOrchestrator()
    try:
        result = await orchestrator.cancel_and_recover(
            booking_id=booking_id,
            failure_type=body.failure_type,
            reason=body.reason,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Disputes ───────────────────────────────────────────────────────────────

@app.post("/api/v1/disputes", tags=["Disputes"])
async def raise_dispute(body: DisputeBody):
    orchestrator = UstaadOrchestrator()
    try:
        result = await orchestrator.resolve_dispute(body.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/disputes/{dispute_id}", tags=["Disputes"])
async def get_dispute(dispute_id: str):
    db = get_db()
    result = db.table("disputes").select("*").eq("id", dispute_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return result.data

# ─── Reviews ────────────────────────────────────────────────────────────────

@app.post("/api/v1/reviews", tags=["Reviews"])
async def submit_review(body: ReviewBody):
    db = get_db()
    try:
        # Sentiment score from rating
        sentiment = (body.rating - 1) / 4.0

        result = db.table("reviews").insert({
            "booking_id": body.booking_id,
            "provider_id": body.provider_id,
            "user_id": body.user_id,
            "rating": body.rating,
            "sentiment_score": sentiment,
            "review_text": body.review_text,
            "complaint_type": body.complaint_type,
        }).execute()

        # Update provider avg_rating
        reviews = db.table("reviews").select("rating") \
            .eq("provider_id", body.provider_id).execute()
        ratings = [r["rating"] for r in (reviews.data or [])]
        new_avg = sum(ratings) / len(ratings) if ratings else body.rating

        db.table("providers").update({
            "avg_rating": round(new_avg, 2),
            "review_count": len(ratings),
        }).eq("id", body.provider_id).execute()

        return {"success": True, "review": result.data[0] if result.data else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Traces ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/traces/{booking_id}", tags=["Traces"])
async def get_traces(booking_id: str):
    """Get the full Antigravity decision trace timeline for a booking."""
    db = get_db()
    result = db.table("traces").select("*") \
        .eq("booking_id", booking_id) \
        .order("timestamp").execute()
    return {
        "booking_id": booking_id,
        "traces": result.data or [],
        "trace_count": len(result.data or []),
    }

@app.get("/api/v1/traces/session/{session_id}", tags=["Traces"])
async def get_session_traces(session_id: str):
    """Get all traces for an orchestration session."""
    db = get_db()
    result = db.table("traces").select("*") \
        .eq("session_id", session_id) \
        .order("timestamp").execute()
    return {
        "session_id": session_id,
        "traces": result.data or [],
    }

# ─── Weather ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/weather/surge", tags=["Weather"])
async def get_weather_surge(lat: Optional[float] = None, lng: Optional[float] = None):
    """Get current weather and surge pricing status."""
    import httpx
    from config import OPENWEATHER_API_KEY, OPENWEATHER_CITY

    temp = 38.0
    if OPENWEATHER_API_KEY:
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
                temp = float(data["main"]["temp"])
        except Exception:
            pass

    if temp < 38:
        surge_tier = "normal"
        surge_amount = 0
    elif temp < 40:
        surge_tier = "warm"
        surge_amount = 200
    elif temp < 43:
        surge_tier = "hot"
        surge_amount = 400
    elif temp < 47:
        surge_tier = "extreme"
        surge_amount = 800
    else:
        surge_tier = "critical"
        surge_amount = 1200

    return {
        "city": OPENWEATHER_CITY,
        "temperature_celsius": temp,
        "is_heatwave": temp > 40,
        "surge_tier": surge_tier,
        "surge_amount_pkr": surge_amount,
        "surge_message": (
            f"Heatwave surge active: PKR {surge_amount} added due to {temp}°C"
            if temp > 40 else "No surge. Normal pricing."
        ),
    }

# ─── Analytics Dashboard ─────────────────────────────────────────────────────

@app.get("/api/v1/analytics/dashboard", tags=["Analytics"])
async def get_dashboard():
    db = get_db()
    try:
        total_providers = db.table("providers").select("id", count="exact").execute().count
        active_providers = db.table("providers").select("id", count="exact").eq("active_status", True).execute().count
        total_bookings = db.table("bookings").select("id", count="exact").execute().count
        confirmed = db.table("bookings").select("id", count="exact").eq("status", "confirmed").execute().count
        completed = db.table("bookings").select("id", count="exact").eq("status", "completed").execute().count
        cancelled = db.table("bookings").select("id", count="exact").eq("status", "cancelled").execute().count
        recovered = db.table("bookings").select("id", count="exact").eq("status", "recovered").execute().count
        disputed = db.table("bookings").select("id", count="exact").eq("status", "disputed").execute().count

        # Top providers
        top = db.table("providers").select("id,name,trust_score,avg_rating,cancellation_rate") \
            .eq("active_status", True).order("trust_score", desc=True).limit(5).execute()

        # Recent traces
        recent_traces = db.table("traces").select("*").order("timestamp", desc=True).limit(20).execute()

        return {
            "providers": {
                "total": total_providers,
                "active": active_providers,
            },
            "bookings": {
                "total": total_bookings,
                "confirmed": confirmed,
                "completed": completed,
                "cancelled": cancelled,
                "recovered": recovered,
                "disputed": disputed,
                "recovery_rate": f"{(recovered / max(cancelled, 1) * 100):.0f}%",
            },
            "top_providers": top.data or [],
            "recent_traces": recent_traces.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Stress Test Scenarios ────────────────────────────────────────────────────

STRESS_SCENARIOS = {
    "provider_cancellation": {
        "text": "AC cooling nahi kar raha, kal morning chahiye",
        "description": "Provider cancels after booking — Recovery Agent activates",
        "simulate_cancel": True,
    },
    "heatwave_surge": {
        "text": "AC band ho gaya abhi zaroorat hai",
        "description": "43°C heatwave — surge pricing + reduced availability",
        "override_temp": 43.5,
    },
    "low_confidence_input": {
        "text": "kuch theek nahi ho raha ghar mein",
        "description": "Vague multilingual input — Intent Agent requests clarification",
    },
    "critical_inverter": {
        "text": "Solar inverter band ho gaya load shedding mein backup nahi aa raha urgent hai",
        "description": "Critical Solar Inverter failure during load shedding — Priority escalation",
    },
    "same_technician_conflict": {
        "text": "AC repair chahiye aaj",
        "description": "Two simultaneous requests for same technician — Scheduling conflict resolution",
    },
    "no_providers_available": {
        "text": "HVAC installation karwani hai aaj",
        "description": "No providers available — Recovery Agent expands radius",
    },
    "fake_high_rated": {
        "text": "Refrigerator repair, trusted technician chahiye",
        "description": "Trust Agent flags fake high-rated provider based on fraud risk",
    },
    "price_dispute": {
        "text": "",
        "description": "Customer raises overcharging dispute — Dispute Agent resolves",
        "is_dispute": True,
        "dispute_data": {
            "dispute_type": "overcharging",
            "description": "Technician charged PKR 5000 but quote was PKR 2500",
            "quoted_price": 2500,
            "actual_charged": 5000,
        },
    },
    "traffic_delay": {
        "text": "Washing machine repair chahiye abhi",
        "description": "Traffic delays detected — Scheduling Agent adds buffer time",
    },
    "maps_api_failure": {
        "text": "AC repair urgent hai",
        "description": "Maps API unavailable — Recovery Agent uses manual estimates",
    },
}

@app.get("/api/v1/simulate/scenarios", tags=["Stress Tests"])
async def list_scenarios():
    return {
        "scenarios": [
            {"id": k, "description": v["description"]}
            for k, v in STRESS_SCENARIOS.items()
        ]
    }

@app.post("/api/v1/simulate/{scenario_id}", tags=["Stress Tests"])
async def run_stress_test(scenario_id: str, body: StressTestBody):
    """Run a specific stress test scenario."""
    if scenario_id not in STRESS_SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}. "
                            f"Valid: {list(STRESS_SCENARIOS.keys())}")

    scenario = STRESS_SCENARIOS[scenario_id]
    orchestrator = UstaadOrchestrator()

    try:
        # Dispute scenario
        if scenario.get("is_dispute"):
            dispute_data = scenario["dispute_data"].copy()
            dispute_data["booking_id"] = str(uuid.uuid4())
            result = await orchestrator.resolve_dispute(dispute_data)
            return {
                "scenario": scenario_id,
                "description": scenario["description"],
                "result": result,
            }

        # Override weather for heatwave scenario
        if "override_temp" in scenario:
            import httpx
            # Monkey-patch weather for demo
            orchestrator._get_weather_temp = lambda **kwargs: scenario["override_temp"]

        # Run full request
        request_data = {
            "text": scenario["text"],
            "lat": body.lat,
            "lng": body.lng,
        }
        result = await orchestrator.process_request(request_data)

        # Simulate cancellation for provider_cancellation scenario
        if scenario.get("simulate_cancel") and result.get("booking"):
            booking_id = result["booking"].get("id")
            if booking_id:
                recovery_result = await orchestrator.cancel_and_recover(
                    booking_id=booking_id,
                    failure_type="provider_cancelled",
                    reason="Technician reported emergency — unavailable",
                )
                result["recovery_simulation"] = recovery_result

        return {
            "scenario": scenario_id,
            "description": scenario["description"],
            "result": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario failed: {str(e)}")

# ─── Notifications ────────────────────────────────────────────────────────────

@app.get("/api/v1/notifications/{user_id}", tags=["Notifications"])
async def get_notifications(user_id: str, unread_only: bool = False):
    db = get_db()
    query = db.table("notifications").select("*").eq("user_id", user_id)
    if unread_only:
        query = query.eq("is_read", False)
    result = query.order("created_at", desc=True).limit(50).execute()
    return {"notifications": result.data or []}

@app.put("/api/v1/notifications/{notification_id}/read", tags=["Notifications"])
async def mark_notification_read(notification_id: str):
    db = get_db()
    db.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    return {"success": True}

# ─── Engineers ─────────────────────────────────────────────────────────────────

class EngineerRegisterBody(BaseModel):
    name: str
    phone: str
    city: str
    area: Optional[str] = ""
    specialization: List[str] = []
    visiting_fee: int = 500
    experience_years: int = 1
    service_prices: dict = {}
    user_id: Optional[str] = None

class AvailabilityBody(BaseModel):
    status: str  # available, busy, offline

@app.post("/api/v1/engineers/register", tags=["Engineers"])
async def register_engineer(body: EngineerRegisterBody):
    """Register a new engineer/provider."""
    db = get_db()
    try:
        provider_data = {
            "name": body.name,
            "phone": body.phone,
            "city": body.city,
            "area": body.area,
            "specialization": body.specialization,
            "experience_years": body.experience_years,
            "active_status": True,
            "is_verified": False,
            "trust_score": 50.0,
            "price_ranges": body.service_prices,
            "visiting_fee": body.visiting_fee,
            "service_prices": body.service_prices,
            "availability_status": "available",
        }
        if body.user_id:
            provider_data["user_id"] = body.user_id

        result = db.table("providers").insert(provider_data).execute()
        provider = result.data[0] if result.data else {}

        # Also create service_pricing records
        for service, price in body.service_prices.items():
            try:
                db.table("service_pricing").insert({
                    "provider_id": provider.get("id"),
                    "service_type": service,
                    "visiting_fee": body.visiting_fee,
                    "min_price": price,
                    "city": body.city,
                }).execute()
            except Exception:
                pass

        return {"success": True, "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/engineers/{provider_id}/dashboard", tags=["Engineers"])
async def get_engineer_dashboard(provider_id: str):
    """Get engineer's dashboard data."""
    db = get_db()
    try:
        provider = db.table("providers").select("*").eq("id", provider_id).single().execute()
        jobs = db.table("bookings").select("*") \
            .eq("provider_id", provider_id) \
            .order("created_at", desc=True).limit(10).execute()
        pricing = db.table("service_pricing").select("*") \
            .eq("provider_id", provider_id).execute()
        return {
            "provider": provider.data or {},
            "recent_jobs": jobs.data or [],
            "pricing": pricing.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/v1/engineers/{provider_id}/availability", tags=["Engineers"])
async def update_engineer_availability(provider_id: str, body: AvailabilityBody):
    """Update engineer's availability status."""
    if body.status not in ["available", "busy", "offline"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    db = get_db()
    try:
        db.table("providers").update({
            "availability_status": body.status,
            "active_status": body.status != "offline",
        }).eq("id", provider_id).execute()
        return {"success": True, "status": body.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/cities/{city}/pricing", tags=["Engineers"])
async def get_city_pricing(city: str, service_type: Optional[str] = None):
    """Get all service pricing for a city — shown to clients before booking."""
    db = get_db()
    try:
        query = db.table("service_pricing").select(
            "*, providers(name, avg_rating, trust_score, is_verified, is_premium)"
        ).eq("city", city)
        if service_type:
            query = query.eq("service_type", service_type)
        result = query.order("min_price").limit(50).execute()
        return {"city": city, "pricing": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

