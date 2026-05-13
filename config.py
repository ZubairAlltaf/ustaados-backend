"""
UstaadOS — Central Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Maps & Weather
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_CITY = os.getenv("OPENWEATHER_CITY", "Lahore")

# App
APP_ENV = os.getenv("APP_ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "ustaad-os-secret-key-2026")
APP_VERSION = "1.0.0"

# Pricing Constants (PKR)
BASE_PRICES = {
    "AC Repair": 1500,
    "Refrigerator Repair": 1200,
    "Washing Machine Repair": 1000,
    "Solar Inverter Repair": 2000,
    "HVAC Installation": 3500,
}

INSPECTION_FEES = {
    "AC Repair": 800,
    "Refrigerator Repair": 600,
    "Washing Machine Repair": 500,
    "Solar Inverter Repair": 1000,
    "HVAC Installation": 1200,
}

TRAVEL_COST_PER_KM = {
    "AC Repair": 50,
    "Refrigerator Repair": 50,
    "Washing Machine Repair": 50,
    "Solar Inverter Repair": 60,
    "HVAC Installation": 60,
}

URGENCY_FEES = {
    "low": 0,
    "medium": 300,
    "high": 500,
    "critical": 1000,
}

HEATWAVE_SURGES = {
    "normal": 0,      # < 38°C
    "warm": 200,      # 38-40°C
    "hot": 400,       # 40-43°C
    "extreme": 800,   # 43-47°C
    "critical": 1200, # > 47°C
}

# Trust Score Thresholds
TRUST_HIGH = 75.0
TRUST_MEDIUM = 50.0
TRUST_LOW = 30.0
FRAUD_RISK_THRESHOLD = 40.0
CANCELLATION_RISK_THRESHOLD = 35.0
