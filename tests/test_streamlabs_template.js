"use strict";
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { runInNewContext } = require("node:vm");
const { test } = require("node:test");

const window = {};
const source = readFileSync(join(__dirname, "../docs/editor/streamlabs.js"), "utf8");
runInNewContext(source, { window });
const { convert } = window.SLB_STREAMLABS;

test("maps donation and bits amounts to their actual event fields", () => {
  assert.equal(convert("Gracias {name}: {amount}", "donation"), "Gracias {user}: {amount} {currency}");
  assert.equal(convert("{name}<br/>envió {amount}", "bits"), "{user}\nenvió {bits}");
});
test("explains unsupported fields instead of losing them silently", () => {
  assert.throws(() => convert("{name} lleva {months} meses ({gifter})", "sub"), /\{months\}.*\{gifter\}/);
  assert.throws(() => convert("{name}", "constructor"), /Elige un evento/);
});
test("doesn't accept widget URLs or external HTML", () => {
  assert.throws(() => convert("https://streamlabs.com/widgets/alert-box/example", "follow"), /No pegues enlaces/);
  assert.throws(() => convert("<img src=x> {name}", "follow"), /Usa texto/);
  assert.equal(convert("¡Gracias por seguir, {name}!", "follow"), "¡Gracias por seguir, {user}!");
});
