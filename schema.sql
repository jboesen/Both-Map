-- Run this in Supabase SQL editor to set up the schema.
-- Supabase Auth handles the auth.users table automatically.

create table if not exists profiles (
  id          uuid references auth.users on delete cascade primary key,
  substack_url      text,
  substack_email    text,
  substack_password text,          -- stored only if user wants autopilot publishing
  cognitive_profile jsonb not null default '{
    "version": 1,
    "last_updated": null,
    "topics": {"covered": [], "interests": [], "exclusions": []},
    "mental_models": [],
    "third_order": [],
    "tone_preferences": {"style": "", "depth": "", "avoid": ""},
    "feedback_history": []
  }'::jsonb,
  cron_schedule_hours integer not null default 24,
  onboarded   boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists pipeline_runs (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references auth.users on delete cascade not null,
  created_at timestamptz not null default now(),
  topic      text,
  post_url   text,
  audio_url  text,
  status     text not null,        -- 'success' | 'error'
  error      text
);

-- Index for fetching a user's run history
create index if not exists pipeline_runs_user_id_idx on pipeline_runs (user_id, created_at desc);

-- Row Level Security: users can only see their own data
alter table profiles enable row level security;
alter table pipeline_runs enable row level security;

create policy "Users can read own profile"
  on profiles for select using (auth.uid() = id);

create policy "Users can update own profile"
  on profiles for update using (auth.uid() = id);

create policy "Users can insert own profile"
  on profiles for insert with check (auth.uid() = id);

create policy "Users can read own runs"
  on pipeline_runs for select using (auth.uid() = user_id);

-- Service role bypasses RLS (used by the backend with service role key)

-- Storage: audio bucket (set to public so audio URLs work without auth)
insert into storage.buckets (id, name, public)
values ('audio', 'audio', true)
on conflict do nothing;
