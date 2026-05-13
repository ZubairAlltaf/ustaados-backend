-- ============================================================
-- UstaadOS — Schema Additions (run in Supabase SQL Editor)
-- Safe to run on top of existing schema — only ADDs new things
-- ============================================================

-- Add role column to users (customer, engineer, admin)
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'customer'
  CHECK (role IN ('customer', 'engineer', 'admin'));

-- Add engineer-specific fields to providers
ALTER TABLE public.providers
  ADD COLUMN IF NOT EXISTS visiting_fee INT DEFAULT 500,
  ADD COLUMN IF NOT EXISTS service_prices JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS coverage_radius_km INT DEFAULT 15,
  ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS availability_status TEXT DEFAULT 'available';

-- Drop and recreate check constraint for availability_status safely
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'providers_availability_status_check'
  ) THEN
    ALTER TABLE public.providers
      ADD CONSTRAINT providers_availability_status_check
      CHECK (availability_status IN ('available', 'busy', 'offline'));
  END IF;
END$$;

-- Index for premium engineers lookup
CREATE INDEX IF NOT EXISTS idx_providers_premium ON public.providers(is_premium, trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_providers_availability ON public.providers(availability_status, city);

-- ============================================================
-- CHAT SESSIONS TABLE (persist chat history per user)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
  messages JSONB DEFAULT '[]',
  last_message_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own chat sessions" ON public.chat_sessions
  FOR ALL USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON public.chat_sessions(user_id, last_message_at DESC);

-- ============================================================
-- SERVICE PRICING TABLE (engineer's listed prices per service)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.service_pricing (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id UUID REFERENCES public.providers(id) ON DELETE CASCADE,
  service_type TEXT NOT NULL,
  visiting_fee INT DEFAULT 500,
  min_price INT DEFAULT 1000,
  max_price INT DEFAULT 5000,
  description TEXT,
  includes_parts BOOLEAN DEFAULT FALSE,
  city TEXT DEFAULT 'Lahore',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.service_pricing ENABLE ROW LEVEL SECURITY;

-- Service pricing is publicly readable (shown to clients)
CREATE POLICY "Service pricing is public" ON public.service_pricing
  FOR SELECT USING (true);

-- Engineers can manage their own pricing
CREATE POLICY "Engineers manage own pricing" ON public.service_pricing
  FOR ALL USING (
    provider_id IN (
      SELECT id FROM public.providers WHERE user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS idx_service_pricing_provider ON public.service_pricing(provider_id);
CREATE INDEX IF NOT EXISTS idx_service_pricing_city ON public.service_pricing(city, service_type);

-- ============================================================
-- ENGINEER APPLICATIONS TABLE (pending verification)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.engineer_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  city TEXT NOT NULL,
  area TEXT,
  specializations TEXT[] DEFAULT '{}',
  experience_years INT DEFAULT 0,
  visiting_fee INT DEFAULT 500,
  cnic TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  rejection_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.engineer_applications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own applications" ON public.engineer_applications
  FOR ALL USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_engineer_apps_status ON public.engineer_applications(status, created_at DESC);

-- Auto-update updated_at on new tables
CREATE TRIGGER update_service_pricing_updated_at
  BEFORE UPDATE ON public.service_pricing
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_engineer_apps_updated_at
  BEFORE UPDATE ON public.engineer_applications
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
