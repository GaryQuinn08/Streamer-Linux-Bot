begin;

-- The public gallery must never expose auth.users or account email.
create table public.overlay_submissions (
  id uuid primary key default gen_random_uuid(),
  creator_user uuid not null default auth.uid() references auth.users(id) on delete cascade,
  creator_name text not null check (char_length(btrim(creator_name)) between 2 and 60),
  description text not null check (char_length(btrim(description)) between 10 and 280),
  license text not null check (license in ('CC0-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0')),
  design jsonb not null check (
    jsonb_typeof(design) = 'object'
    and design ? 'mode'
    and coalesce(design->>'mode', '') in ('alert', 'chat', 'events')
    and coalesce(char_length(btrim(design->>'name')), 0) between 1 and 60
    and octet_length(design::text) <= 60000
    and not (design ?| array['url','script','javascript','owner','creator_user','status','email'])
  ),
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz not null default now()
);
create index overlay_submissions_creator_created on public.overlay_submissions (creator_user, created_at desc);
create table public.overlay_publications (
  id uuid primary key references public.overlay_submissions(id) on delete cascade,
  creator_name text not null,
  description text not null,
  license text not null,
  design jsonb not null,
  published_at timestamptz not null default now()
);

alter table public.overlay_submissions enable row level security;
alter table public.overlay_publications enable row level security;
revoke all on table public.overlay_submissions, public.overlay_publications from public, anon, authenticated;

grant select (id, creator_name, description, license, design, status, created_at)
  on public.overlay_submissions to authenticated;
grant select (id, creator_name, description, license, design, published_at)
  on public.overlay_publications to anon, authenticated;
grant insert (creator_name, description, license, design)
  on public.overlay_submissions to authenticated;

create policy overlay_submissions_read_own on public.overlay_submissions
  for select to authenticated using ((select auth.uid()) = creator_user);
create policy overlay_submissions_insert_own on public.overlay_submissions
  for insert to authenticated with check (
    (select auth.uid()) = creator_user and status = 'pending'
    and (select auth.jwt()->'app_metadata'->>'provider') = 'google'
  );
create policy overlay_publications_read on public.overlay_publications
  for select to anon, authenticated using (true);

-- Explicit moderator actions from SQL editor or a trusted service, not from the site.
create function public.review_overlay_submission(submission_id uuid, approve boolean)
returns void
language plpgsql security definer set search_path = ''
as $$
declare
  item public.overlay_submissions%rowtype;
begin
  if approve is null then
    raise exception 'Expected approve true or false';
  end if;
  select * into strict item from public.overlay_submissions where id = submission_id for update;
  if approve then
    insert into public.overlay_publications(id, creator_name, description, license, design)
      values (item.id, item.creator_name, item.description, item.license, item.design)
      on conflict (id) do update set creator_name = excluded.creator_name,
        description = excluded.description, license = excluded.license, design = excluded.design;
    update public.overlay_submissions set status = 'approved' where id = submission_id;
  else
    delete from public.overlay_publications where id = submission_id;
    update public.overlay_submissions set status = 'rejected' where id = submission_id;
  end if;
end;
$$;
revoke all on function public.review_overlay_submission(uuid, boolean) from public, anon, authenticated;
grant execute on function public.review_overlay_submission(uuid, boolean) to service_role;

-- Per-account cap prevents accidental rapid resubmissions; advisory lock closes races.
create function public.limit_overlay_submissions() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(new.creator_user::text, 0));
  if (select count(*) from public.overlay_submissions
    where creator_user = new.creator_user and created_at > now() - interval '24 hours') >= 10 then
    raise exception 'Daily submission limit reached';
  end if;
  return new;
end;
$$;
revoke all on function public.limit_overlay_submissions() from public, anon, authenticated;
create trigger limit_overlay_submissions before insert on public.overlay_submissions
  for each row execute function public.limit_overlay_submissions();

commit;
