-- ============================================================
-- UstaadOS — Supabase PostgreSQL Schema
-- Run this in Supabase SQL Editor
-- ============================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- USERS TABLE (extends Supabase Auth)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT UNIQUE,
  email TEXT UNIQUE,
  city TEXT DEFAULT 'Lahore',
  address TEXT,
  lat DECIMAL(10,7),
  lng DECIMAL(10,7),
  preferred_language TEXT DEFAULT 'roman_urdu',
  loyalty_points INT DEFAULT 0,
  total_bookings INT DEFAULT 0,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PROVIDERS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.providers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  name TEXT NOT NULL,
  phone TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE,
  city TEXT NOT NULL DEFAULT 'Lahore',
  area TEXT,
  lat DECIMAL(10,7),
  lng DECIMAL(10,7),
  specialization TEXT[] DEFAULT '{}',
  skills TEXT[] DEFAULT '{}',
  bio TEXT,
  experience_years INT DEFAULT 0,
  avg_rating DECIMAL(3,2) DEFAULT 0.0,
  review_count INT DEFAULT 0,
  cancellation_rate DECIMAL(5,2) DEFAULT 0.0,
  punctuality_score DECIMAL(5,2) DEFAULT 100.0,
  trust_score DECIMAL(5,2) DEFAULT 50.0,
  fraud_risk DECIMAL(5,2) DEFAULT 0.0,
  response_time_minutes INT DEFAULT 30,
  completion_rate DECIMAL(5,2) DEFAULT 100.0,
  repeat_customer_ratio DECIMAL(5,2) DEFAULT 0.0,
  active_status BOOLEAN DEFAULT TRUE,
  is_verified BOOLEAN DEFAULT FALSE,
  workload INT DEFAULT 0,
  max_daily_jobs INT DEFAULT 5,
  price_ranges JSONB DEFAULT '{}',
  available_slots JSONB DEFAULT '[]',
  total_earnings DECIMAL(12,2) DEFAULT 0,
  total_jobs_completed INT DEFAULT 0,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- BOOKINGS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.bookings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.users(id),
  provider_id UUID REFERENCES public.providers(id),
  service_type TEXT NOT NULL,
  issue_type TEXT,
  issue_description TEXT,
  urgency_level TEXT DEFAULT 'medium' CHECK (urgency_level IN ('low','medium','high','critical')),
  severity_score DECIMAL(3,1) DEFAULT 0.0,
  status TEXT DEFAULT 'pending' CHECK (status IN (
    'pending','confirmed','in_progress','completed','cancelled',
    'recovery_needed','recovery_in_progress','recovered','disputed'
  )),
  user_lat DECIMAL(10,7),
  user_lng DECIMAL(10,7),
  user_address TEXT,
  scheduled_time TIMESTAMPTZ,
  estimated_duration_minutes INT DEFAULT 60,
  actual_start_time TIMESTAMPTZ,
  actual_end_time TIMESTAMPTZ,
  price DECIMAL(10,2),
  price_breakdown JSONB DEFAULT '{}',
  trust_snapshot JSONB DEFAULT '{}',
  match_reasoning TEXT,
  cancellation_reason TEXT,
  cancelled_by TEXT,
  recovery_attempts INT DEFAULT 0,
  original_provider_id UUID,
  is_heatwave_surge BOOLEAN DEFAULT FALSE,
  weather_temp DECIMAL(5,2),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TRACES TABLE (Antigravity Decision Log)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.traces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID REFERENCES public.bookings(id) ON DELETE CASCADE,
  session_id TEXT,
  agent_name TEXT NOT NULL,
  observation TEXT,
  reasoning TEXT,
  decision TEXT,
  action TEXT,
  outcome TEXT,
  recovery TEXT,
  confidence_score DECIMAL(3,2) DEFAULT 0.0,
  execution_time_ms INT DEFAULT 0,
  metadata JSONB DEFAULT '{}',
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- REVIEWS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID REFERENCES public.bookings(id) UNIQUE,
  provider_id UUID REFERENCES public.providers(id),
  user_id UUID REFERENCES public.users(id),
  rating INT CHECK (rating BETWEEN 1 AND 5),
  sentiment_score DECIMAL(3,2) DEFAULT 0.0,
  complaint_type TEXT,
  review_text TEXT,
  response_text TEXT,
  is_verified BOOLEAN DEFAULT FALSE,
  helpful_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DISPUTES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.disputes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  booking_id UUID REFERENCES public.bookings(id) UNIQUE,
  user_id UUID REFERENCES public.users(id),
  provider_id UUID REFERENCES public.providers(id),
  dispute_type TEXT CHECK (dispute_type IN (
    'overcharging','poor_quality','incomplete_work',
    'no_show','delayed_arrival','fake_diagnosis','other'
  )),
  description TEXT,
  quoted_price DECIMAL(10,2),
  actual_charged DECIMAL(10,2),
  evidence_urls TEXT[] DEFAULT '{}',
  status TEXT DEFAULT 'open' CHECK (status IN ('open','investigating','resolved','escalated','closed')),
  resolution TEXT,
  refund_amount DECIMAL(10,2) DEFAULT 0,
  ai_verdict TEXT,
  ai_confidence DECIMAL(3,2) DEFAULT 0.0,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PROVIDER SCHEDULES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.provider_schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id UUID REFERENCES public.providers(id) ON DELETE CASCADE,
  booking_id UUID REFERENCES public.bookings(id),
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  status TEXT DEFAULT 'booked' CHECK (status IN ('booked','available','blocked','completed')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- NOTIFICATIONS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS public.notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.users(id),
  provider_id UUID REFERENCES public.providers(id),
  booking_id UUID REFERENCES public.bookings(id),
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  is_read BOOLEAN DEFAULT FALSE,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_providers_city ON public.providers(city);
CREATE INDEX IF NOT EXISTS idx_providers_active ON public.providers(active_status);
CREATE INDEX IF NOT EXISTS idx_providers_trust ON public.providers(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON public.bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_provider ON public.bookings(provider_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON public.bookings(status);
CREATE INDEX IF NOT EXISTS idx_traces_booking ON public.traces(booking_id);
CREATE INDEX IF NOT EXISTS idx_traces_session ON public.traces(session_id);
CREATE INDEX IF NOT EXISTS idx_reviews_provider ON public.reviews(provider_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON public.notifications(user_id, is_read);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.disputes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY "Users see own profile" ON public.users
  FOR ALL USING (auth.uid() = id);

-- Bookings: users see own, providers see their bookings
CREATE POLICY "Users see own bookings" ON public.bookings
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users create bookings" ON public.bookings
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Providers are publicly readable
CREATE POLICY "Providers are public" ON public.providers
  FOR SELECT USING (true);

-- Traces are publicly readable (for demo transparency)
CREATE POLICY "Traces are public" ON public.traces
  FOR SELECT USING (true);

-- Reviews are publicly readable
CREATE POLICY "Reviews are public" ON public.reviews
  FOR SELECT USING (true);

-- Notifications: users see own
CREATE POLICY "Users see own notifications" ON public.notifications
  FOR ALL USING (auth.uid() = user_id);

-- ============================================================
-- REALTIME PUBLICATIONS
-- ============================================================
ALTER PUBLICATION supabase_realtime ADD TABLE public.bookings;
ALTER PUBLICATION supabase_realtime ADD TABLE public.traces;
ALTER PUBLICATION supabase_realtime ADD TABLE public.notifications;

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_providers_updated_at
  BEFORE UPDATE ON public.providers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_bookings_updated_at
  BEFORE UPDATE ON public.bookings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-create user profile after auth signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, full_name, email, phone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', 'User'),
    NEW.email,
    NEW.phone
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
