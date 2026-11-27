const fs=require('node:fs'), assert=require('node:assert/strict');
const {PGlite}=require('@electric-sql/pglite');
(async()=>{
 const db=new PGlite();
 const u='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', v='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
 try {
 await db.exec(`
 create role anon; create role authenticated; create role service_role; create schema auth;
 create table auth.users(id uuid primary key);
 grant usage on schema auth to anon, authenticated, service_role;
 create function auth.jwt() returns jsonb language sql stable as $$ select current_setting('request.jwt.claims',true)::jsonb $$;
 create function auth.uid() returns uuid language sql stable as $$ select (auth.jwt()->>'sub')::uuid $$;
 insert into auth.users values ('${u}'),('${v}');
 `);
 for (const f of ['202611260501_overlay_community.sql','202611260550_overlay_catalog.sql','202611260610_overlay_profiles_packs.sql'])
   await db.exec(fs.readFileSync('supabase/migrations/'+f,'utf8'));
 const q=(...args)=>db.query(...args); const session=(role,sub,provider='google')=>db.exec(`reset role; set role ${role}; set request.jwt.claims to '${JSON.stringify({sub,app_metadata:{provider}})}';`);
 const submit=()=>q(`insert into public.overlay_submissions (creator_name,description,license,design) values ('Spoofed','Descripción de prueba','CC0-1.0','{"mode":"alert","name":"Demo Overlay"}')`);
 const base={format:'slb-pack',version:1,name:'Test tema',description:'Tema de prueba',components:[{kind:'camera',design:{name:'Marco',mode:'static',accent:'#ab00df',css:'omit',script:'omit'}},{kind:'chat',design:{name:'Chat',mode:'chat'}}]};
 const publish=(p=base)=>q("select public.publish_overlay_pack($1::jsonb,'CC0-1.0') as id",[JSON.stringify(p)]);
 await session('anon',null);
 assert.equal((await q("select count(*)::int as n from public.overlay_catalog_stats where design_key like 'theme:%'")).rows[0].n,20);
 await assert.rejects(()=>q('select display_name from public.overlay_profiles'));
 await assert.rejects(()=>publish());
 await session('authenticated',u,'github');
 await assert.rejects(()=>q("select public.save_overlay_profile('Another user','')"),/Google sign-in required/);
 await session('authenticated',u);
 await assert.rejects(()=>q('select public.enable_overlay_creator()'),/Save your profile first/);
 await q("select public.save_overlay_profile('Alicia','Biografía privada')");
 assert.deepEqual((await q('select display_name,bio,is_creator from public.overlay_profiles')).rows[0],{display_name:'Alicia',bio:'Biografía privada',is_creator:false});
 await assert.rejects(submit,/Enable the editor/);
 await assert.rejects(()=>publish(),/Enable the editor/);
 await q('select public.enable_overlay_creator()');
 await q("select public.save_overlay_profile('Alicia','Cambio privado')");
 assert.equal((await q('select is_creator from public.overlay_profiles')).rows[0].is_creator,true);
 await submit();
 assert.equal((await q('select creator_name from public.overlay_publications')).rows[0].creator_name,'Alicia');
 await assert.rejects(()=>publish({...base,components:[base.components[0],base.components[0]]}),/duplicate/);
 const {id}=(await publish()).rows[0];
 assert.equal((await q('select * from public.my_overlay_packs()')).rows[0].id,id);
 await q('select public.rate_overlay($1,5)',['pack:'+id]);
 await session('authenticated',v);
 assert.deepEqual((await q('select display_name,bio,is_creator from public.overlay_profiles')).rows,[]);
 assert.deepEqual((await q('select * from public.my_overlay_packs()')).rows,[]);
 await session('anon',null);
 await assert.rejects(()=>q('select owner_id from public.overlay_pack_publications'));
 const row=(await q('select id,creator_name,pack from public.overlay_pack_publications')).rows[0];
 assert.equal(row.creator_name,'Alicia'); assert.equal(row.pack.components[0].design.mode,'static');
 assert.ok(!Object.hasOwn(row.pack.components[0].design,'css')&&!Object.hasOwn(row.pack.components[0].design,'script'));
 await q('select public.record_overlay_download($1,gen_random_uuid())',['pack:'+id]);
 assert.equal(Number((await q('select downloads from public.overlay_catalog_stats where design_key=$1',['pack:'+id])).rows[0].downloads),1);
 console.log('PASS: profiles independent from uploads, privacy, creator opt-in, authored singles/packs, validated pack schema, twenty themes and public metrics.');
 } finally {await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
