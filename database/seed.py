"""
UstaadOS — Database Seed Script
Generates realistic Pakistani technician data:
  - 100 providers
  - 1000 bookings
  - 500 reviews
  - cancellation & trust histories
"""
import json
import random
import sys
import os
import uuid
from datetime import datetime, timedelta
from faker import Faker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

try:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
except Exception as e:
    print(f"Supabase connection failed: {e}")
    supabase = None

fake = Faker('en_PK')
random.seed(42)

# ─── Pakistani Cities & Areas ──────────────────────────────────────────────
CITIES = ["Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad",
          "Multan", "Peshawar", "Bahawalpur", "Sialkot", "Gujranwala"]

LAHORE_AREAS = [
    "DHA Phase 1", "DHA Phase 2", "DHA Phase 5", "Gulberg III", "Gulberg V",
    "Model Town", "Johar Town", "Bahria Town", "Garden Town", "Shadman",
    "Iqbal Town", "Township", "Wapda Town", "Faisal Town", "Lake City"
]

COORDS = {
    "DHA Phase 1": (31.4697, 74.4014),
    "DHA Phase 2": (31.4754, 74.3812),
    "DHA Phase 5": (31.4755, 74.4059),
    "Gulberg III": (31.5120, 74.3360),
    "Gulberg V": (31.5204, 74.3401),
    "Model Town": (31.4876, 74.3321),
    "Johar Town": (31.4698, 74.2680),
    "Bahria Town": (31.3637, 74.1985),
    "Garden Town": (31.5012, 74.3398),
    "Shadman": (31.5329, 74.3289),
    "Iqbal Town": (31.4876, 74.3143),
    "Township": (31.4567, 74.3012),
    "Wapda Town": (31.4437, 74.2987),
    "Faisal Town": (31.5021, 74.3209),
    "Lake City": (31.5637, 74.5012),
}

# ─── Service Categories ─────────────────────────────────────────────────────
SERVICES = [
    "AC Repair", "Refrigerator Repair", "Washing Machine Repair",
    "Solar Inverter Repair", "HVAC Installation"
]

SERVICE_ISSUES = {
    "AC Repair": ["Cooling Failure", "Gas Leakage", "Compressor Issue",
                  "Remote Not Working", "Water Leakage", "Noise Problem",
                  "Not Turning On", "Electrical Fault"],
    "Refrigerator Repair": ["Not Cooling", "Compressor Noise", "Ice Maker Issue",
                             "Water Dispenser Fault", "Door Seal Damaged",
                             "Temperature Fluctuation", "Electrical Fault"],
    "Washing Machine Repair": ["Not Spinning", "Drainage Issue", "Noise Problem",
                                "Not Starting", "Water Leakage", "Control Panel Issue",
                                "Door Lock Fault"],
    "Solar Inverter Repair": ["Inverter Failure", "Battery Not Charging",
                               "Output Power Low", "Display Error",
                               "Overheating", "No Output", "Load Shedding Issue"],
    "HVAC Installation": ["New Installation", "Duct Installation",
                           "System Upgrade", "Maintenance Setup",
                           "Multi-Zone Setup"],
}

SKILLS_MAP = {
    "AC Repair": ["AC Repair", "HVAC", "Refrigeration", "Electrical"],
    "Refrigerator Repair": ["Refrigerator Repair", "Refrigeration", "Electrical"],
    "Washing Machine Repair": ["Washing Machine Repair", "Electrical", "Plumbing"],
    "Solar Inverter Repair": ["Solar Systems", "Inverter Repair", "Electrical", "Battery Systems"],
    "HVAC Installation": ["HVAC Installation", "AC Repair", "Duct Work", "Electrical"],
}

PAKISTANI_NAMES = [
    "Muhammad Ali", "Ahmed Hassan", "Bilal Khan", "Usman Raza", "Tariq Mahmood",
    "Asif Iqbal", "Zubair Ahmad", "Shahid Latif", "Nadeem Baig", "Imran Butt",
    "Salman Malik", "Kamran Sheikh", "Waseem Akbar", "Rizwan Hussain", "Farrukh Noor",
    "Javed Anwar", "Nasir Mehmood", "Tanveer Gill", "Babar Aziz", "Umer Farooq",
    "Hassan Rauf", "Saad Khan", "Khurram Shah", "Danish Manzoor", "Sohail Akhtar",
    "Faisal Nawaz", "Qasim Ali", "Waqar Ahmed", "Noman Riaz", "Adeel Siddiqui",
    "Mudassar Iqbal", "Shehroz Butt", "Jawad Hameed", "Arslan Yousuf", "Hamza Cheema",
    "Talha Mirza", "Moeen Abbasi", "Zain ul Abideen", "Furqan Rashid", "Haris Kamal",
    "Anas Shafiq", "Raza Haider", "Ahsan Gul", "Sameer Lodhi", "Waheed Zafar",
    "Irfan Chaudhry", "Mubashir Anwar", "Nabil Rana", "Ghazanfar Ali", "Sajid Mehmood",
    "Amjad Hussain", "Pervaiz Gill", "Iftikhar Bajwa", "Naveed Sultan", "Asad Warsi",
    "Tauseef Qureshi", "Liaquat Dar", "Arshad Pirzada", "Aamir Bhatti", "Farhan Lodhi",
    "Sibtain Zaidi", "Majid Khattak", "Zaheer Abbas", "Mirza Baig", "Shakeel Pasha",
    "Iqbal Chishti", "Maqsood Elahi", "Rashid Kakar", "Bashir Tareen", "Atif Channa",
    "Daud Khawaja", "Ghulam Mustafa", "Habib ur Rehman", "Imdad Soomro", "Junaid Baloch",
    "Khaled Jatoi", "Latif Magsi", "Muneer Unar", "Naseem Palijo", "Owais Chandio",
    "Pervez Talpur", "Qadeer Leghari", "Rahim Lund", "Sarfraz Korejo", "Tanvir Lashari",
    "Umar Abro", "Vaqar Hussain", "Waris Ali", "Xander Malik", "Yasir Keerio",
    "Zafar Bhutto", "Abdul Hafeez", "Basharat Memon", "Changez Khan", "Dilshad Brohi",
    "Ejaz Ujjan", "Fateh Marri", "Gohar Zaman", "Hamid Gul", "Idrees Talpir",
    "Jahangir Wattoo", "Kashif Noon", "Lokman Virk", "Munir Awan", "Noor Hassan"
]

PRICE_RANGES = {
    "AC Repair": {"min": 1500, "max": 8000},
    "Refrigerator Repair": {"min": 1200, "max": 6000},
    "Washing Machine Repair": {"min": 1000, "max": 5000},
    "Solar Inverter Repair": {"min": 2000, "max": 12000},
    "HVAC Installation": {"min": 15000, "max": 80000},
}


def random_date(start_days_ago: int, end_days_ago: int = 0):
    start = datetime.now() - timedelta(days=start_days_ago)
    end = datetime.now() - timedelta(days=end_days_ago)
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate_providers():
    providers = []
    for i in range(100):
        name = PAKISTANI_NAMES[i]
        area = random.choice(LAHORE_AREAS)
        coord = COORDS.get(area, (31.5204, 74.3587))
        lat = coord[0] + random.uniform(-0.05, 0.05)
        lng = coord[1] + random.uniform(-0.05, 0.05)

        # Assign 1-3 specializations
        num_specs = random.randint(1, 3)
        specialization = random.sample(SERVICES, num_specs)

        # Build skills
        skills = []
        for spec in specialization:
            skills.extend(SKILLS_MAP.get(spec, []))
        skills = list(set(skills))

        # Generate realistic trust metrics
        experience = random.randint(1, 20)

        # Experienced techs tend to have better scores
        experience_factor = min(experience / 20, 1.0)

        # Some bad actors (10% of providers)
        is_bad_actor = random.random() < 0.10

        if is_bad_actor:
            avg_rating = round(random.uniform(2.5, 3.8), 2)
            cancellation_rate = round(random.uniform(30, 60), 2)
            punctuality_score = round(random.uniform(30, 55), 2)
            trust_score = round(random.uniform(15, 35), 2)
            fraud_risk = round(random.uniform(35, 70), 2)
            completion_rate = round(random.uniform(40, 70), 2)
            repeat_ratio = round(random.uniform(0, 10), 2)
        else:
            avg_rating = round(random.uniform(3.5, 5.0) * experience_factor + random.uniform(3.0, 3.8) * (1 - experience_factor), 2)
            avg_rating = min(5.0, max(1.0, avg_rating))
            cancellation_rate = round(max(0, random.gauss(8 - experience_factor * 5, 5)), 2)
            punctuality_score = round(min(100, random.gauss(75 + experience_factor * 20, 10)), 2)
            trust_score = round(min(100, 40 + experience_factor * 40 + avg_rating * 5 - cancellation_rate * 0.5), 2)
            fraud_risk = round(max(0, random.gauss(5, 8)), 2)
            completion_rate = round(min(100, random.gauss(88 + experience_factor * 10, 8)), 2)
            repeat_ratio = round(min(100, random.gauss(20 + experience_factor * 30, 10)), 2)

        # Price ranges
        price_ranges_data = {}
        for spec in specialization:
            pr = PRICE_RANGES[spec]
            price_ranges_data[spec] = {
                "min": pr["min"],
                "max": pr["max"],
                "inspection_fee": int(pr["min"] * 0.4),
            }

        # Available slots (next 7 days)
        available_slots = []
        for day_offset in range(1, 8):
            day = datetime.now() + timedelta(days=day_offset)
            for hour in [9, 11, 14, 16]:
                if random.random() > 0.3:  # 70% chance slot is free
                    slot_time = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                    available_slots.append(slot_time.isoformat())

        provider = {
            "id": str(uuid.uuid4()),
            "name": name,
            "phone": f"03{random.randint(100000000, 499999999)}",
            "email": f"{name.lower().replace(' ', '.')}{random.randint(1,99)}@gmail.com",
            "city": "Lahore",
            "area": area,
            "lat": round(lat, 7),
            "lng": round(lng, 7),
            "specialization": specialization,
            "skills": skills,
            "bio": f"Professional technician with {experience} years of experience in {', '.join(specialization[:2])}.",
            "experience_years": experience,
            "avg_rating": avg_rating,
            "review_count": random.randint(5, 500),
            "cancellation_rate": cancellation_rate,
            "punctuality_score": punctuality_score,
            "trust_score": trust_score,
            "fraud_risk": fraud_risk,
            "response_time_minutes": random.choice([15, 20, 30, 45, 60]),
            "completion_rate": completion_rate,
            "repeat_customer_ratio": repeat_ratio,
            "active_status": True,
            "is_verified": random.random() < 0.6,
            "workload": random.randint(0, 4),
            "max_daily_jobs": random.choice([4, 5, 6]),
            "price_ranges": price_ranges_data,
            "available_slots": available_slots,
            "total_jobs_completed": random.randint(10, 2000),
            "total_earnings": round(random.uniform(50000, 5000000), 2),
        }
        providers.append(provider)

    return providers


def generate_bookings(providers):
    bookings = []
    statuses = ["completed"] * 70 + ["cancelled"] * 15 + ["disputed"] * 5 + ["in_progress"] * 5 + ["confirmed"] * 5
    urgency_levels = ["low"] * 20 + ["medium"] * 45 + ["high"] * 25 + ["critical"] * 10

    for i in range(1000):
        provider = random.choice(providers)
        service = random.choice(provider["specialization"]) if provider["specialization"] else random.choice(SERVICES)
        issue = random.choice(SERVICE_ISSUES.get(service, ["General Repair"]))
        urgency = random.choice(urgency_levels)
        status = random.choice(statuses)

        scheduled = random_date(180, 0)
        price_range = PRICE_RANGES.get(service, {"min": 1000, "max": 5000})
        base_price = random.uniform(price_range["min"] * 0.8, price_range["max"] * 0.9)

        urgency_fee = {"low": 0, "medium": 300, "high": 500, "critical": 1000}.get(urgency, 0)
        heatwave = random.random() < 0.3
        heatwave_fee = random.choice([0, 400, 800]) if heatwave else 0
        travel_fee = random.randint(100, 500)
        total = base_price + urgency_fee + heatwave_fee + travel_fee

        area = random.choice(LAHORE_AREAS)
        coord = COORDS.get(area, (31.5204, 74.3587))

        booking = {
            "id": str(uuid.uuid4()),
            "user_id": None,  # Will be linked when users exist
            "provider_id": provider["id"],
            "service_type": service,
            "issue_type": issue,
            "issue_description": f"Customer reported: {issue.lower()} in {area}",
            "urgency_level": urgency,
            "severity_score": round(random.uniform(1.0, 5.0), 1),
            "status": status,
            "user_lat": round(coord[0] + random.uniform(-0.02, 0.02), 7),
            "user_lng": round(coord[1] + random.uniform(-0.02, 0.02), 7),
            "user_address": f"House {random.randint(1,500)}, Block {random.choice('ABCDEFGH')}, {area}, Lahore",
            "scheduled_time": scheduled.isoformat(),
            "estimated_duration_minutes": random.choice([60, 90, 120, 180]),
            "price": round(total, 2),
            "price_breakdown": {
                "base_fee": round(base_price, 2),
                "inspection_fee": int(price_range["min"] * 0.4),
                "travel_cost": travel_fee,
                "urgency_fee": urgency_fee,
                "heatwave_surge": heatwave_fee,
                "complexity_fee": random.randint(0, 500),
                "loyalty_discount": random.choice([0, 0, 0, 100, 200]),
                "total": round(total, 2),
            },
            "trust_snapshot": {
                "trust_score": provider["trust_score"],
                "cancellation_rate": provider["cancellation_rate"],
                "avg_rating": provider["avg_rating"],
            },
            "is_heatwave_surge": heatwave,
            "weather_temp": round(random.uniform(28, 48), 1) if heatwave else round(random.uniform(20, 38), 1),
            "created_at": (scheduled - timedelta(hours=random.randint(1, 48))).isoformat(),
        }

        if status == "cancelled":
            booking["cancellation_reason"] = random.choice([
                "Provider unavailable", "Customer cancelled", "Emergency", "Rescheduled"
            ])
            booking["cancelled_by"] = random.choice(["provider", "user"])
            booking["recovery_attempts"] = random.randint(0, 2)

        bookings.append(booking)

    return bookings


def generate_reviews(providers, bookings):
    reviews = []
    completed_bookings = [b for b in bookings if b["status"] == "completed"]
    sample_size = min(500, len(completed_bookings))
    selected = random.sample(completed_bookings, sample_size)

    complaint_types = [None, None, None, "overcharging", "late_arrival",
                       "poor_quality", "incomplete_work", "rude_behavior"]

    for booking in selected:
        provider = next((p for p in providers if p["id"] == booking["provider_id"]), None)
        if not provider:
            continue

        # Bad actors more likely to get low ratings
        is_bad = provider["fraud_risk"] > 35
        rating = random.randint(1, 3) if is_bad else random.randint(3, 5)
        sentiment = round((rating - 1) / 4, 2)  # Normalize to 0-1

        review = {
            "id": str(uuid.uuid4()),
            "booking_id": booking["id"],
            "provider_id": booking["provider_id"],
            "user_id": None,
            "rating": rating,
            "sentiment_score": sentiment,
            "complaint_type": random.choice(complaint_types) if rating <= 3 else None,
            "review_text": _generate_review_text(rating, booking["service_type"]),
            "is_verified": True,
            "created_at": (
                datetime.fromisoformat(booking["scheduled_time"]) + timedelta(hours=random.randint(2, 24))
            ).isoformat(),
        }
        reviews.append(review)

    return reviews


def _generate_review_text(rating: int, service: str) -> str:
    positive = [
        f"Excellent work on {service}! Very professional.",
        f"Highly recommend! Fixed the issue quickly.",
        f"Great service, punctual and skilled technician.",
        f"Very satisfied with the {service} repair. Will book again.",
        f"Professional and honest. Fair pricing.",
    ]
    neutral = [
        f"Work was done but took longer than expected.",
        f"Okay service, but room for improvement.",
        f"Got the job done. Average experience.",
    ]
    negative = [
        f"Arrived late and charged more than quoted for {service}.",
        f"Poor quality work. Issue still not resolved.",
        f"Not satisfied. Would not recommend.",
        f"Overcharged and unprofessional behavior.",
    ]

    if rating >= 4:
        return random.choice(positive)
    elif rating == 3:
        return random.choice(neutral)
    else:
        return random.choice(negative)


def run_seed():
    print("🌱 UstaadOS Database Seeder")
    print("=" * 50)

    print("\n📊 Generating 100 providers...")
    providers = generate_providers()

    print("📅 Generating 1000 bookings...")
    bookings = generate_bookings(providers)

    print("⭐ Generating 500 reviews...")
    reviews = generate_reviews(providers, bookings)

    if supabase:
        print("\n🚀 Uploading to Supabase...")
        try:
            # Upload providers in batches
            batch_size = 20
            for i in range(0, len(providers), batch_size):
                batch = providers[i:i + batch_size]
                supabase.table("providers").upsert(batch).execute()
                print(f"  ✅ Providers: {min(i + batch_size, len(providers))}/100")

            # Upload bookings (no user_id for seed)
            for i in range(0, len(bookings), batch_size):
                batch = bookings[i:i + batch_size]
                # Remove user_id for seed data
                for b in batch:
                    b.pop("user_id", None)
                supabase.table("bookings").upsert(batch).execute()
                print(f"  ✅ Bookings: {min(i + batch_size, len(bookings))}/1000")

            # Upload reviews
            for i in range(0, len(reviews), batch_size):
                batch = reviews[i:i + batch_size]
                for r in batch:
                    r.pop("user_id", None)
                supabase.table("reviews").upsert(batch).execute()
                print(f"  ✅ Reviews: {min(i + batch_size, len(reviews))}/500")

            print("\n✅ Seed complete! Database ready.")
        except Exception as e:
            print(f"\n❌ Supabase error: {e}")
            print("💾 Saving to local JSON files instead...")
            _save_local(providers, bookings, reviews)
    else:
        print("\n💾 No Supabase connection. Saving to local JSON...")
        _save_local(providers, bookings, reviews)


def _save_local(providers, bookings, reviews):
    os.makedirs("seed_data", exist_ok=True)
    with open("seed_data/providers.json", "w") as f:
        json.dump(providers, f, indent=2, default=str)
    with open("seed_data/bookings.json", "w") as f:
        json.dump(bookings, f, indent=2, default=str)
    with open("seed_data/reviews.json", "w") as f:
        json.dump(reviews, f, indent=2, default=str)
    print(f"  💾 providers.json ({len(providers)} records)")
    print(f"  💾 bookings.json ({len(bookings)} records)")
    print(f"  💾 reviews.json ({len(reviews)} records)")
    print("\n✅ Local seed files saved in backend/seed_data/")


if __name__ == "__main__":
    run_seed()
