begin;

create table public.overlay_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 2 and 60),
  bio text not null default '' check (char_length(bio) <= 240),
  is_creator boolean not null default false
);
alter table public.overlay_profiles enable row level security;
revoke all on public.overlay_profiles from public, anon, authenticated;
grant select (display_name,bio,is_creator) on public.overlay_profiles to authenticated;
create policy overlay_profiles_read_own on public.overlay_profiles for select to authenticated
  using ((select auth.uid()) = user_id);

create function overlay_catalog_private.google_user() returns uuid
language plpgsql stable set search_path = '' as $$
declare u uuid := auth.uid();
begin
  if u is null or (auth.jwt()->'app_metadata'->>'provider') is distinct from 'google' then
    raise exception 'Google sign-in required';
  end if;
  return u;
end;
$$;

create function public.save_overlay_profile(p_display_name text,p_bio text) returns void
language plpgsql security definer set search_path = '' as $$
declare u uuid := overlay_catalog_private.google_user();
begin
  insert into public.overlay_profiles(user_id,display_name,bio)
    values (u,btrim(p_display_name),btrim(coalesce(p_bio,'')))
    on conflict (user_id) do update set display_name=excluded.display_name,bio=excluded.bio;
end;
$$;
revoke all on function public.save_overlay_profile(text,text) from public, anon, authenticated;
grant execute on function public.save_overlay_profile(text,text) to authenticated;

create function public.enable_overlay_creator() returns void
language plpgsql security definer set search_path = '' as $$
begin
  update public.overlay_profiles set is_creator=true where user_id=overlay_catalog_private.google_user();
  if not found then raise exception 'Save your profile first'; end if;
end;
$$;
revoke all on function public.enable_overlay_creator() from public, anon, authenticated;
grant execute on function public.enable_overlay_creator() to authenticated;

create function overlay_catalog_private.editor_alias(u uuid) returns text
language plpgsql stable set search_path = '' as $$
declare result text;
begin
  select display_name into result from public.overlay_profiles where user_id=u and is_creator;
  if not found then raise exception 'Enable the editor in your profile first'; end if;
  return result;
end;
$$;

create function overlay_catalog_private.use_editor_alias() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  new.creator_name := overlay_catalog_private.editor_alias(overlay_catalog_private.google_user());
  return new;
end;
$$;
create trigger ab_overlay_require_creator before insert on public.overlay_submissions
  for each row execute function overlay_catalog_private.use_editor_alias();

create table public.overlay_pack_publications (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  creator_name text not null,
  description text not null,
  license text not null check (license in ('CC0-1.0','CC-BY-4.0','CC-BY-SA-4.0')),
  pack jsonb not null,
  published_at timestamptz not null default now()
);
create index overlay_packs_owner_date on public.overlay_pack_publications(owner_id,published_at desc);
create index overlay_packs_date on public.overlay_pack_publications(published_at desc);
alter table public.overlay_pack_publications enable row level security;
revoke all on public.overlay_pack_publications from public, anon, authenticated;
grant select (id,creator_name,description,license,pack,published_at) on public.overlay_pack_publications to anon, authenticated;
create policy overlay_pack_public_read on public.overlay_pack_publications for select to anon,authenticated using (true);

create function overlay_catalog_private.clean_pack(p jsonb) returns jsonb
language plpgsql immutable set search_path = '' as $$
declare
  piece jsonb;
  k text;
  d jsonb;
  flags text[] := array[]::text[];
  kept jsonb := '[]'::jsonb;
begin
  if jsonb_typeof(p) is distinct from 'object' or octet_length(p::text) > 60000
    or p->>'format' is distinct from 'slb-pack' or p->'version' is distinct from '1'::jsonb
    or jsonb_typeof(p->'name') is distinct from 'string'
    or char_length(btrim(p->>'name')) not between 1 and 60
    or jsonb_typeof(p->'description') is distinct from 'string'
    or char_length(p->>'description') > 280
    or jsonb_typeof(p->'components') is distinct from 'array' then raise exception 'Invalid theme format';
  end if;
  if jsonb_array_length(p->'components') not between 1 and 8 then raise exception 'Invalid theme component count'; end if;
  for piece in select value from jsonb_array_elements(p->'components') loop
    k := piece->>'kind';
    if k is null or k not in ('alert','chat','events','banner','camera','starting','brb','ending')
      or k = any(flags) or jsonb_typeof(piece->'design') is distinct from 'object' then
      raise exception 'Invalid or duplicate theme component';
    end if;
    flags := array_append(flags,k);
    d := overlay_catalog_private.visual_only(piece->'design');
    d := d || jsonb_build_object('mode',case when k in ('alert','chat','events') then k else 'static' end);
    if coalesce(char_length(btrim(d->>'name')),0) = 0 then raise exception 'Missing component name'; end if;
    kept := kept || jsonb_build_array(jsonb_build_object('kind',k,'design',d));
  end loop;
  return jsonb_build_object('format','slb-pack','version',1,'name',btrim(p->>'name'),
    'description',btrim(p->>'description'),'components',kept);
end;
$$;

create function public.publish_overlay_pack(p_pack jsonb,p_license text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  u uuid := overlay_catalog_private.google_user();
  alias text := overlay_catalog_private.editor_alias(u);
  result uuid;
  cleaned jsonb;
begin
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('pack:' || u::text,0));
  if (select count(*) from public.overlay_pack_publications where owner_id=u
      and published_at > now()-interval '24 hours') >= 5 then raise exception 'Daily theme limit reached'; end if;
  cleaned := overlay_catalog_private.clean_pack(p_pack);
  insert into public.overlay_pack_publications(owner_id,creator_name,description,license,pack)
    values (u,alias,cleaned->>'description',p_license,cleaned) returning id into result;
  return result;
end;
$$;
revoke all on function public.publish_overlay_pack(jsonb,text) from public, anon, authenticated;
grant execute on function public.publish_overlay_pack(jsonb,text) to authenticated;

create function public.my_overlay_packs()
returns table(id uuid,creator_name text,description text,license text,pack jsonb,published_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select p.id,p.creator_name,p.description,p.license,p.pack,p.published_at
  from public.overlay_pack_publications p where p.owner_id=overlay_catalog_private.google_user()
  order by p.published_at desc limit 40;
$$;
revoke all on function public.my_overlay_packs() from public, anon, authenticated;
grant execute on function public.my_overlay_packs() to authenticated;

create table overlay_catalog_private.official_themes (slug text primary key);
insert into overlay_catalog_private.official_themes values
 ('neon-nocturno'),('bosque-lunar'),('costa-coral'),('grano-retro'),('terminal-verde'),
 ('tinta-sakura'),('horizonte-solar'),('hielo-polar'),('polvo-marciano'),('patio-menta'),
 ('arcade-ochobits'),('gruta-amatista'),('mapa-estelar'),('jardin-de-papel'),('ferrita-industrial'),
 ('marea-profunda'),('vitral-aurora'),('cafe-de-medianoche'),('circuito-carbon'),('prisma-mate');
create or replace view overlay_catalog_private.keys as
  select 'gallery:' || slug as design_key from overlay_catalog_private.curated
  union all select 'community:' || id::text from public.overlay_publications
  union all select 'theme:' || slug from overlay_catalog_private.official_themes
  union all select 'pack:' || id::text from public.overlay_pack_publications;

notify pgrst, 'reload schema';
commit;
