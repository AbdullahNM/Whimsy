/**
 * tests/test_core_parity.js
 * =========================
 * Node.js test runner suite for Core.resolve equivalence over the shared fixture corpus.
 */

const fs = require('fs');
const path = require('path');
const test = require('node:test');
const assert = require('node:assert');
const { Core, Outcome } = require('../UI/core/deterministic_core.js');

test('Core Parity - Shared Fixture Corpus Equivalence', (t) => {
  const fixturesDir = path.resolve(__dirname, 'fixtures/outcomes');
  const files = fs.readdirSync(fixturesDir).filter(f => f.endsWith('.json')).sort();

  assert.ok(files.length >= 10, 'Expected at least 10 fixtures in the shared corpus');

  function sortKeys(val) {
    if (Array.isArray(val)) return val.map(sortKeys);
    if (val !== null && typeof val === 'object') {
      const sorted = {};
      for (const k of Object.keys(val).sort()) sorted[k] = sortKeys(val[k]);
      return sorted;
    }
    return val;
  }

  for (const file of files) {
    t.test(`Fixture: ${file}`, () => {
      const content = fs.readFileSync(path.join(fixturesDir, file), 'utf8');
      const fix = JSON.parse(content);
      const outcome = Core.resolve(fix.state, fix.action, fix.config);
      const outcomeJson = outcome.toJson();
      const expectedJson = JSON.stringify(sortKeys(fix.expected_outcome), null, 2);

      assert.strictEqual(
        outcomeJson,
        expectedJson,
        `Node outcome diverged from expected outcome in ${file}`
      );
    });
  }
});

test('Core - Outcome JSON roundtrip', () => {
  const sample = {
    version: 1,
    effects: [{ type: 'stat_change', target: 'energy', delta: -5, previous: 100, current: 95 }],
    events: ['Clock filled: test'],
    clocks_advanced: [{ id: 'test', label: 'test', delta: 1, previous: 3, current: 4, max: 4, fired: true }],
    progression_delta: { energy: -5 },
    resources_delta: { credits: 50 },
    offered_choices: [{ index: 1, text: 'Continue' }],
    next_state: { turn: 2 }
  };
  const outcome = Outcome.fromDict(sample);
  const jsonStr = outcome.toJson();
  const reconstructed = Outcome.fromJson(jsonStr);

  assert.deepStrictEqual(reconstructed.toDict(), outcome.toDict());
});
