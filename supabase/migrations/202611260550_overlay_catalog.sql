begin;

-- This is additive: old pending submissions stay private. Only future uploads are published.
create schema overlay_catalog_private;
revoke all on schema overlay_catalog_private from public, anon, authenticated;

-- Community publications are regenerated from bounded visual settings, not user markup.
create function overlay_catalog_private.visual_only(original jsonb) returns jsonb
language sql immutable set search_path = '' as $$
  select coalesce(jsonb_object_agg(key,value),'{}'::jsonb)
  from jsonb_each(original)
  where
    (key = 'mode' and jsonb_typeof(value) = 'string' and (value #>> '{}') in ('alert','chat','events'))
    or (jsonb_typeof(value) = 'string' and
      ((key = 'name' and char_length(value #>> '{}') between 1 and 60)
        or (key = 'title' and char_length(value #>> '{}') <= 220)
        or (key = 'body' and char_length(value #>> '{}') <= 380)
        or (key in ('accent','textColor','background') and (value #>> '{}') ~ '^#[0-9a-fA-F]{6}$')
        or (key in ('enter','exit') and (value #>> '{}') in ('none','fade','slide-up','slide-left','zoom','pop'))
        or (key = 'align' and (value #>> '{}') in ('left','center','right'))))
    or (key = 'showPlatform' and jsonb_typeof(value) = 'boolean')
    or (case when jsonb_typeof(value) = 'number' then
      (value #>> '{}')::numeric >= 0 and
        (value #>> '{}')::numeric <= case key
          when 'duration' then 300 when 'size' then 72 when 'max' then 24
          when 'opacity' then 100 when 'enterMs' then 3000 when 'exitMs' then 3000
          when 'positionX' then 100 when 'positionY' then 100 when 'width' then 100
          when 'radius' then 48 when 'padding' then 48 when 'border' then 16
          else -1 end
      else false end);
$$;

create function overlay_catalog_private.clean_submission() returns trigger
language plpgsql set search_path = '' as $$
begin
  if jsonb_typeof(new.design) is distinct from 'object' or octet_length(new.design::text) > 60000 then
    raise exception 'Invalid overlay design';
  end if;
  new.design := overlay_catalog_private.visual_only(new.design);
  return new;
end;
$$;
-- The trigger runs the exact same sanitizer for SQL/API callers, not just the web form.
alter function overlay_catalog_private.clean_submission() security definer;

create function overlay_catalog_private.publish_submission() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  perform public.review_overlay_submission(new.id, true);
  return null;
end;
$$;
create trigger aa_overlay_sanitize before insert on public.overlay_submissions
  for each row execute function overlay_catalog_private.clean_submission();
create trigger overlay_publish_after_insert after insert on public.overlay_submissions
  for each row execute function overlay_catalog_private.publish_submission();

create table overlay_catalog_private.curated (
  slug text primary key
);
insert into overlay_catalog_private.curated values
 ('aurora'),('comunidad'),('pulso'),('orbita'),('pixel-pop'),('nyx'),('estudio'),('mercurio'),
 ('retro-fm'),('brasa'),('violeta'),('marea');
create view overlay_catalog_private.keys as
  select 'gallery:' || slug as design_key from overlay_catalog_private.curated
  union all select 'community:' || id::text from public.overlay_publications;

create table overlay_catalog_private.ratings (
  design_key text not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  stars integer not null check (stars between 1 and 5),
  primary key (design_key,user_id)
);

create table overlay_catalog_private.downloads (
  design_key text primary key,
  downloads bigint not null default 0 check (downloads >= 0)
);

create table overlay_catalog_private.download_requests (
  nonce uuid primary key,
  seen_at timestamptz not null default now()
);
create index download_requests_seen_at on overlay_catalog_private.download_requests(seen_at);

create view public.overlay_catalog_stats with (security_barrier = true) as
  select k.design_key, coalesce(d.downloads,0::bigint) as downloads,
    coalesce(r.rating_count,0) as rating_count, r.rating_average
  from overlay_catalog_private.keys k
  left join overlay_catalog_private.downloads d using (design_key)
  left join (
    select design_key, count(*)::integer as rating_count, round(avg(stars),2) as rating_average
    from overlay_catalog_private.ratings group by design_key
  ) r using (design_key);
revoke all on public.overlay_catalog_stats from public, anon, authenticated;
grant select on public.overlay_catalog_stats to anon, authenticated;

create function public.rate_overlay(p_key text, p_stars integer) returns void
language plpgsql security definer set search_path = '' as $$
declare voter uuid := auth.uid();
begin
  if voter is null or (auth.jwt()->'app_metadata'->>'provider') is distinct from 'google' then
    raise exception 'Google sign-in required';
  end if;
  if p_stars is null or p_stars not between 1 and 5 then raise exception 'Invalid rating'; end if;
  if length(p_key) > 70 or not exists (select from overlay_catalog_private.keys where design_key=p_key) then
    raise exception 'Design not available';
  end if;
  insert into overlay_catalog_private.ratings values (p_key,voter,p_stars)
    on conflict (design_key,user_id) do update set stars=excluded.stars;
end;
$$;
revoke all on function public.rate_overlay(text,integer) from public, anon, authenticated;
grant execute on function public.rate_overlay(text,integer) to authenticated;

create function public.record_overlay_download(p_key text, p_nonce uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if p_nonce is null or length(p_key) > 70 or
    not exists (select from overlay_catalog_private.keys where design_key=p_key) then
    raise exception 'Design not available';
  end if;
  -- Same event (network retry/double submit) can increment only once. No IP or identity stored.
  insert into overlay_catalog_private.download_requests(nonce) values (p_nonce) on conflict do nothing;
  if not found then return; end if;
  insert into overlay_catalog_private.downloads values (p_key,1)
    on conflict (design_key) do update
      set downloads=overlay_catalog_private.downloads.downloads+1;
  -- Expire bounded batches of stale dedup rows; cumulative totals are not removed.
  delete from overlay_catalog_private.download_requests where nonce in (
    select nonce from overlay_catalog_private.download_requests
    where seen_at < now()-interval '7 days' order by seen_at limit 20
    for update skip locked
  );
end;
$$;
revoke all on function public.record_overlay_download(text,uuid) from public, anon, authenticated;
grant execute on function public.record_overlay_download(text,uuid) to anon, authenticated;
notify pgrst, 'reload schema';
commit;
