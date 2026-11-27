const fs = require('node:fs');
const assert = require('node:assert/strict');
const {PGlite} = require('@electric-sql/pglite');

(async () => {
  const db = new PGlite();
  try {
    const alice = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
    const bob = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
    await db.exec(`
      create role anon; create role authenticated; create role service_role;
      create schema auth;
      create table auth.users(id uuid primary key);
      grant usage on schema auth to anon, authenticated, service_role;
      create function auth.jwt() returns jsonb language sql stable as $$ select current_setting('request.jwt.claims',true)::jsonb $$;
      create function auth.uid() returns uuid language sql stable as $$ select (auth.jwt()->>'sub')::uuid $$;
      insert into auth.users values ('${alice}'),('${bob}');
    `);
    const install = name => db.exec(fs.readFileSync('supabase/migrations/' + name, 'utf8'));
    const session = (role, sub, provider='google') => db.exec(`reset role; set role ${role}; set request.jwt.claims to '${JSON.stringify({sub,app_metadata:{provider}})}';`);
    const submit = design => db.query("insert into public.overlay_submissions(creator_name,description,license,design) values ('Creadora','Descripción de prueba','CC-BY-4.0',$1::jsonb) returning id", [JSON.stringify(design)]);
    const stats = async key => (await db.query('select * from public.overlay_catalog_stats where design_key=$1',[key])).rows[0];
    const rate = (key, stars) => db.query('select public.rate_overlay($1,$2)',[key,stars]);
    const dl = (key, nonce) => db.query('select public.record_overlay_download($1,$2)',[key, nonce]);

    await install('202611260501_overlay_community.sql');
    await session('authenticated', alice);
    const {id: old} = (await submit({mode:'alert',name:'Pendiente anterior'})).rows[0];
    await db.exec('reset role');
    await install('202611260550_overlay_catalog.sql');
    await session('anon', null);
    assert.equal(await stats('community:'+old),undefined);
    assert.equal((await db.query('select count(*)::int as count from public.overlay_publications')).rows[0].count,0);
    assert.equal((await db.query('select count(*)::int as count from public.overlay_catalog_stats')).rows[0].count,12);
    await assert.rejects(() => submit({mode:'alert',name:'Anónimo'}));

    await session('authenticated', alice, 'github');
    await assert.rejects(() => submit({mode:'alert',name:'OAuth no permitido'}));
    await assert.rejects(() => rate('gallery:aurora',4),/Google sign-in required/);

    await session('authenticated', alice);
    const {id}=(await submit({mode:'alert',name:'Publicación directa',enter:'pop',width:67,showPlatform:false,accent:'#Aa11bb',css:'body{}',markup:'<p>personal</p>',javascript:'private',unrecognized:'omit',positionX:999})).rows[0];
    const key = 'community:'+id;
    const own=(await db.query('select status,design from public.overlay_submissions where id=$1',[id])).rows[0];
    assert.equal(own.status,'approved');
    assert.deepEqual(own.design,{mode:'alert',name:'Publicación directa',enter:'pop',width:67,showPlatform:false,accent:'#Aa11bb'});
    await assert.rejects(() => db.query('select public.review_overlay_submission($1,false)',[id]));
    await rate(key,4); await rate(key,2);
    assert.equal((await stats(key)).rating_count,1);
    await assert.rejects(() => rate(key,0),/Invalid rating/);
    await assert.rejects(() => rate('gallery:unknown',1),/Design not available/);
    await session('authenticated', bob);
    assert.equal((await db.query('select id from public.overlay_submissions')).rows.length,0);
    await rate(key,5);
    await rate('gallery:aurora',5);
    await session('anon', null);
    await assert.rejects(() => rate(key,3));
    await assert.rejects(() => db.query('select user_id from overlay_catalog_private.ratings'));
    await assert.rejects(() => db.query('select creator_user from public.overlay_publications'));
    assert.deepEqual((await db.query('select design from public.overlay_publications')).rows[0].design,own.design);
    assert.equal((await stats(key)).rating_count,2);
    assert.equal(Number((await stats(key)).rating_average),3.5);
    assert.equal(Number((await stats('gallery:aurora')).rating_average),5);
    const once = '00000000-0000-4000-8000-000000000001';
    const twice = '00000000-0000-4000-8000-000000000002';
    await dl(key,once); await dl(key,once); await dl(key,twice);
    assert.equal(Number((await stats(key)).downloads),2);
    await assert.rejects(() => dl('gallery:unknown',twice));
    await db.exec('reset role');
    await db.query('select public.review_overlay_submission($1,false)',[id]);
    await session('anon', null);
    assert.equal(await stats(key),undefined);
    assert.equal(Number((await stats('gallery:aurora')).downloads),0);
    console.log('PASS: private legacy submissions, direct sanitized publishing, rating identity/upsert, anonymous deduped downloads and retraction.');
  } finally { await db.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
