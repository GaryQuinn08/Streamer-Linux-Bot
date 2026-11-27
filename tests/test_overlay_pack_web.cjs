const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const docs = path.join(__dirname, '..', 'docs');
const catalog = JSON.parse(fs.readFileSync(path.join(docs, 'galeria', 'themes.json'), 'utf8'));
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(docs, 'overlay-pack.js'), 'utf8'), { window, TextEncoder });
const api = window.SLB_PACK;
const pack = (components, options = {}) =>
  ({ format: 'slb-pack', version: 1, name: 'Laboratorio', description: 'De prueba', components, ...options });

test('contains exactly 20 original theme IDs with different visual palette or motif', () => {
  assert.equal(catalog.length, 20);
  assert.equal(new Set(catalog.map(theme => theme.id)).size, 20);
  assert.equal(new Set(catalog.map(theme => theme.art)).size, 20);
  for (const theme of catalog)
    assert.match(theme.id, /^[a-z0-9][a-z0-9-]{0,63}$/);
});

test('normalizes a round trip to only declarative fields; caps Unicode by code points', () => {
  const name = 'a'.repeat(59) + '🌔zzz';
  const raw = pack([{kind:'alert', design:{ ...{ name, title:'x\uD800', mode:'events' }, max:400, size:90,
    background:'#AA11FF', css:'bad:{}', markup:'<img>' }}], {secret:'do not retain'});
  const normalized = api.parse(api.serialize(raw));
  assert.equal(normalized.name, 'Laboratorio');
  assert.deepEqual(Object.keys(normalized), ['format','version','name','description','components']);
  const piece = normalized.components[0];
  assert.equal(piece.design.name, 'a'.repeat(59) + '🌔');
  assert.equal(piece.design.title, 'x\uFFFD');
  assert.equal(piece.design.background, '#aa11ff');
  assert.equal(piece.design.mode, 'alert');
  assert.equal(piece.design.max, 1);
  assert.equal(piece.design.size, 72);
  assert.equal(piece.design.css, undefined);
  assert.equal(piece.design.markup, undefined);
});

test('rejects unsupported version, overlarge data, unknown and duplicate pieces', () => {
  for (const bad of [
    pack([], {version:2}), pack([]), pack([{kind:'webpage',design:{}}]), pack([{kind:'chat',design:[] }]),
    pack([{kind:'chat',design:{}}, {kind:'chat',design:{}}]),
  ]) assert.throws(() => api.parse(JSON.stringify(bad)));
  assert.throws(() => api.parse('🌕'.repeat(32768)), /64 KiB/);
  assert.throws(() => api.parse('{oops}'), /no es JSON/);
});

test('static HTML can be reopened and user-provided markup remains literal', () => {
  const title = '</script><img src="https://invalid.example/x">';
  const piece = api.component('camera', { title, body:'x&y', accent:'#bb1122; color:red' });
  const built = api.buildComponent(piece);
  assert.match(built, /class="outer frame"/);
  assert.match(built, /background:transparent/);
  assert.match(built, /default-src 'none'/);
  assert(!built.includes('<img'));
  assert(built.includes('&lt;/script&gt;&lt;img'));
  assert.equal(api.componentFromHTML(built).design.title, title);
  assert.equal(api.componentFromHTML(built).design.accent, '#9ef3c9');
});
