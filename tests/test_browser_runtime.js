/**
 * tests/test_browser_runtime.js
 * ==============================
 * Comprehensive tests for Issue #17: Browser-Playable Runtime with No Backend Required.
 *
 * Verifies:
 * - R1: Offline execution, keyless turn resolution, zero network required.
 * - R3: IndexedDB save, load, and deterministic replay engine.
 * - R6, R7: Tiered narration adapters (Tier 1 Authored, Tier 2 Local, Tier 3 Cloud)
 *   producing identical deterministic state outcomes (Same Outcome contract).
 * - R8: Narration never gates progress (seamless non-blocking fallback).
 */

const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const fs = require('fs');

const { Core, Outcome } = require('../UI/core/deterministic_core.js');
const { IndexedDBEngine, WhimsyStorage } = require('../UI/storage/indexeddb.js');
const { AuthoredNarrator, authoredNarrator } = require('../UI/narrator/authored_narrator.js');
const { LocalNarrator, localNarrator } = require('../UI/narrator/local_narrator.js');
const { CloudNarrator, cloudNarrator } = require('../UI/narrator/cloud_narrator.js');
const { TieredNarrator, tieredNarrator, TIERS } = require('../UI/narrator/tiered_narrator.js');

// Base test state matching canonical campaign schema
const getInitialTestState = () => ({
  schema_version: 2,
  campaign_id: 'template_campaign',
  turn: 1,
  timeline: 'Act I — Dawn of Chapter One',
  character: {
    name: 'Alex Mercer',
    archetype: 'Independent Specialist'
  },
  progression: {
    energy: 100,
    energy_max: 100,
    stress: 10,
    stress_max: 100
  },
  purse: {
    credits: 500,
    display: '500 ₡'
  },
  public_state: {
    flags: {},
    conditions: [],
    open_threads: ['Decide whether to accept the contract.']
  },
  clocks: [
    {
      id: 'contract_deadline',
      label: 'Contract deadline',
      current: 0,
      max: 4,
      visibility: 'known',
      advance_trigger: 'Time passes without a decision.'
    }
  ],
  scene_anchor: {
    location: 'Staging Room A',
    context: 'Datapad active awaiting input.',
    time: '06:00 Local Cycle'
  },
  pacing_state: {
    elapsed_time_minutes: 0,
    narrative_intensity: 1,
    scheduled_events: [],
    timeline_stamp: '06:00 Local Cycle',
    zoom_level: 'detailed_scene'
  }
});

test('Browser Runtime - IndexedDB Storage Engine (R3)', async (t) => {
  const engine = new IndexedDBEngine();
  await engine.init();

  await t.test('Save and retrieve campaign state', async () => {
    const state = getInitialTestState();
    await engine.saveCampaignState('test_campaign', { state, currentTurn: 1 });

    const retrieved = await engine.getCampaignState('test_campaign');
    assert.ok(retrieved, 'Should retrieve saved campaign');
    assert.strictEqual(retrieved.currentTurn, 1);
    assert.strictEqual(retrieved.state.character.name, 'Alex Mercer');
  });

  await t.test('Save, retrieve, and delete turns in order', async () => {
    await engine.saveTurn('test_campaign', 1, {
      content: '# Turn 1\nAction 1',
      playerAction: '1. Press forward',
      gmResponse: 'You pressed forward.'
    });
    await engine.saveTurn('test_campaign', 2, {
      content: '# Turn 2\nAction 2',
      playerAction: '2. Inspect area',
      gmResponse: 'You inspected the area.'
    });

    const turns = await engine.getTurns('test_campaign');
    assert.strictEqual(turns.length, 2);
    assert.strictEqual(turns[0].turnNumber, 1);
    assert.strictEqual(turns[1].turnNumber, 2);

    const turn1 = await engine.getTurn('test_campaign', 1);
    assert.strictEqual(turn1.playerAction, '1. Press forward');

    await engine.deleteTurn('test_campaign', 1);
    const turnsAfter = await engine.getTurns('test_campaign');
    assert.strictEqual(turnsAfter.length, 1);
    assert.strictEqual(turnsAfter[0].turnNumber, 2);
  });

  await t.test('Export and import save snapshot', async () => {
    const exportData = await engine.exportSave('test_campaign');
    assert.strictEqual(exportData.campaignId, 'test_campaign');
    assert.ok(Array.isArray(exportData.turns));

    const engine2 = new IndexedDBEngine();
    await engine2.init();
    await engine2.importSave(exportData);

    const imported = await engine2.getCampaignState('test_campaign');
    assert.ok(imported);
    assert.strictEqual(imported.currentTurn, 1);
  });

  await t.test('Deterministic replay verification', async () => {
    const replayEngine = new IndexedDBEngine();
    await replayEngine.init();

    const cid = 'replay_test_campaign';
    const initState = getInitialTestState();

    // Step 1: Action 1
    const outcome1 = Core.resolve(initState, '1', { seed: 101, operational_mode: 'classic_cyoa' });
    await replayEngine.recordReplayStep(cid, {
      turnNumber: 1,
      action: '1',
      outcome: outcome1.toDict(),
      initialState: initState
    });

    // Step 2: Action 2
    const outcome2 = Core.resolve(outcome1.next_state, '2', { seed: 102, operational_mode: 'classic_cyoa' });
    await replayEngine.recordReplayStep(cid, {
      turnNumber: 2,
      action: '2',
      outcome: outcome2.toDict()
    });

    // Replay with Core
    const replayResult = await replayEngine.replayCampaign(cid, Core);
    assert.strictEqual(replayResult.success, true, 'Replay should match deterministic outcomes');
    assert.strictEqual(replayResult.turnsReplayed, 2);
    assert.strictEqual(replayResult.finalState.turn, outcome2.next_state.turn);
    assert.strictEqual(replayResult.mismatches.length, 0);
  });
});

test('Browser Runtime - Tier 1 Authored / Offline Narrator (R1, R6)', async (t) => {
  const state = getInitialTestState();
  const outcome = Core.resolve(state, '1', { seed: 42, operational_mode: 'classic_cyoa' });

  const narrative = authoredNarrator.generateNarrative({
    action: '1. Press forward along your primary path.',
    outcome: outcome,
    context: { genre: 'Cyberpunk Noir' }
  });

  assert.ok(typeof narrative === 'string' && narrative.length > 50, 'Narrative must be substantial prose');
  assert.ok(narrative.includes('Alex Mercer') || narrative.includes('Staging Room A'), 'Prose should ground protagonist/location');
  assert.ok(narrative.includes('[OPTIONS]'), 'Prose must contain [OPTIONS] block');
  assert.ok(narrative.includes('1. ') && narrative.includes('2. '), 'Options list must be populated');
});

test('Browser Runtime - Same Outcome Contract Across Tiers (R7)', async (t) => {
  const state = getInitialTestState();
  const action = '1';
  const config = { seed: 505, operational_mode: 'classic_cyoa' };

  // Resolve with Tier 1
  const tier1Res = await tieredNarrator.resolveTurn({
    state: JSON.parse(JSON.stringify(state)),
    action: action,
    config: config,
    preferredTier: TIERS.AUTHORED
  });

  // Resolve with Tier 2 (mock local model responding)
  const mockLocal = {
    generateNarrative: async () => 'Local model prose describing action.\n\n[OPTIONS]\n1. A\n2. B'
  };
  const tier2Narrator = new TieredNarrator();
  tier2Narrator._getLocalNarrator = () => mockLocal;

  const tier2Res = await tier2Narrator.resolveTurn({
    state: JSON.parse(JSON.stringify(state)),
    action: action,
    config: config,
    preferredTier: TIERS.LOCAL
  });

  // Resolve with Tier 3 (mock cloud model responding)
  const mockCloud = {
    isConfigured: () => true,
    generateNarrative: async () => 'Cloud LLM prose describing high-stakes tension.\n\n[OPTIONS]\n1. A\n2. B'
  };
  const tier3Narrator = new TieredNarrator();
  tier3Narrator._getCloudNarrator = () => mockCloud;

  const tier3Res = await tier3Narrator.resolveTurn({
    state: JSON.parse(JSON.stringify(state)),
    action: action,
    config: config,
    preferredTier: TIERS.CLOUD,
    apiKey: 'test-api-key'
  });

  // VERIFY R7: Identical state outcome across all three tiers!
  const outcome1Json = tier1Res.outcome.toJson ? tier1Res.outcome.toJson() : JSON.stringify(tier1Res.outcome);
  const outcome2Json = tier2Res.outcome.toJson ? tier2Res.outcome.toJson() : JSON.stringify(tier2Res.outcome);
  const outcome3Json = tier3Res.outcome.toJson ? tier3Res.outcome.toJson() : JSON.stringify(tier3Res.outcome);

  assert.strictEqual(outcome1Json, outcome2Json, 'Tier 1 and Tier 2 outcomes must be byte-identical');
  assert.strictEqual(outcome1Json, outcome3Json, 'Tier 1 and Tier 3 outcomes must be byte-identical');

  // Verify next state progression & turn matches exactly
  assert.strictEqual(tier1Res.outcome.next_state.turn, 2);
  assert.strictEqual(tier2Res.outcome.next_state.turn, 2);
  assert.strictEqual(tier3Res.outcome.next_state.turn, 2);

  // But prose narratives differ
  assert.notStrictEqual(tier1Res.narration.text, tier2Res.narration.text, 'Prose between tiers can differ');
  assert.notStrictEqual(tier1Res.narration.text, tier3Res.narration.text, 'Prose between tiers can differ');
});

test('Browser Runtime - Narration Never Gates Progress (R8 Fallback)', async (t) => {
  const state = getInitialTestState();
  const action = '1';
  const config = { seed: 999, operational_mode: 'classic_cyoa' };

  // 1. Simulate Cloud Model throwing an error (e.g. invalid key, quota exceeded)
  const failingCloudNarrator = new TieredNarrator();
  failingCloudNarrator._getCloudNarrator = () => ({
    isConfigured: () => true,
    generateNarrative: async () => {
      throw new Error('401 Unauthorized / Insufficient Quota');
    }
  });

  const resCloudFail = await failingCloudNarrator.resolveTurn({
    state: JSON.parse(JSON.stringify(state)),
    action: action,
    config: config,
    preferredTier: TIERS.CLOUD
  });

  assert.strictEqual(resCloudFail.narration.tierUsed, TIERS.AUTHORED, 'Should fallback to Tier 1');
  assert.strictEqual(resCloudFail.narration.fallbackOccurred, true);
  assert.ok(resCloudFail.narration.text.length > 50, 'Authored prose returned despite cloud error');
  assert.strictEqual(resCloudFail.outcome.next_state.turn, 2, 'Game state progressed normally');

  // 2. Simulate Local Model timing out or unreachable
  const failingLocalNarrator = new TieredNarrator();
  failingLocalNarrator._getLocalNarrator = () => ({
    generateNarrative: async () => {
      throw new Error('Failed to fetch from http://localhost:8000/generate');
    }
  });

  const resLocalFail = await failingLocalNarrator.resolveTurn({
    state: JSON.parse(JSON.stringify(state)),
    action: action,
    config: config,
    preferredTier: TIERS.LOCAL
  });

  assert.strictEqual(resLocalFail.narration.tierUsed, TIERS.AUTHORED, 'Should fallback to Tier 1');
  assert.strictEqual(resLocalFail.narration.fallbackOccurred, true);
  assert.strictEqual(resLocalFail.outcome.next_state.turn, 2, 'Game state progressed normally');
});

test('Browser Runtime - CloudNarrator resolves FastRouter vs OpenRouter vs Gemini providers', () => {
  assert.strictEqual(cloudNarrator._resolveProvider('fr-12345', 'fastrouter/openai/gpt-4o-mini'), 'fastrouter');
  assert.strictEqual(cloudNarrator._resolveProvider('sk-or-v1-12345', 'anthropic/claude-3.5-sonnet'), 'openrouter');
  assert.strictEqual(cloudNarrator._resolveProvider('AIzaSyDummyKey123', 'gemini-2.5-flash'), 'gemini');
  assert.strictEqual(cloudNarrator._resolveProvider('custom-key', 'my-model', 'fastrouter'), 'fastrouter');
});

test('Browser Runtime - LocalNarrator requires pre-turn state, preserves explicit currentTurn, and isolates generic endpoints', async (t) => {
  const originalFetch = global.fetch;

  const buildTurn5State = () => {
    const s = getInitialTestState();
    s.campaign_id = 'harbor_chronicle';
    s.turn = 5;
    s.progression.energy = 80;
    s.progression.stress = 15;
    s.scene_anchor.location = 'Bellwether Pier';
    return s;
  };

  const turn5Config = {
    seed: 777,
    operational_mode: 'classic_cyoa',
    rules: [
      {
        match: { choice_index: 1 },
        progression_delta: { energy: -10 },
        next_choices: [
          { index: 1, text: 'Unseal the brine-stained harbor ledger' },
          { index: 2, text: 'Signal the customs skiff from the jetty' }
        ]
      }
    ]
  };

  await t.test('Native bridge rejects missing pre-turn state instead of sending resolved next_state', async () => {
    let fetchCalled = false;
    global.fetch = async () => {
      fetchCalled = true;
      return { ok: true, json: async () => ({ response: 'should not happen' }) };
    };
    try {
      const preState = buildTurn5State();
      const outcome = Core.resolve(preState, '1', turn5Config);
      await assert.rejects(
        () => localNarrator.generateNarrative({
          action: '1',
          outcome,
          endpoint: 'http://localhost:8000/generate',
          campaign: 'harbor_chronicle',
          currentTurn: 5
        }),
        /pre-turn state/i
      );
      assert.strictEqual(fetchCalled, false, 'fetch must not run when pre-turn state is absent');
    } finally {
      global.fetch = originalFetch;
    }
  });

  await t.test('Explicit currentTurn is preserved over differing outcome.next_state.turn (non-template Turn 5 scenario)', async () => {
    const calls = [];
    global.fetch = async (url, init) => {
      calls.push({ url, headers: init.headers, body: JSON.parse(init.body) });
      return {
        ok: true,
        json: async () => ({
          response: (
            'Brine slicks the piling as you pry the clasp free.\n\n' +
            '### [OPTIONS & TYPABLE REFERENCE]\n' +
            '1. Unseal the brine-stained harbor ledger\n' +
            '2. Signal the customs skiff from the jetty\n\n' +
            '[SYS: Turn 6 | Energy: 70 / 100 | Checkpoints: 5/5]'
          )
        })
      };
    };

    try {
      const preState = buildTurn5State();
      const res = await tieredNarrator.resolveTurn({
        state: preState,
        action: '1',
        config: turn5Config,
        preferredTier: TIERS.LOCAL,
        localEndpoint: 'http://127.0.0.1:8000/generate',
        campaign: 'harbor_chronicle',
        currentTurn: 5,
        commit: true
      });

      assert.strictEqual(calls.length, 1);
      const sent = calls[0].body;
      assert.strictEqual(sent.campaign, 'harbor_chronicle');
      assert.strictEqual(sent.currentTurn, 5);
      assert.strictEqual(sent.state.turn, 5, 'native bridge must receive pre-turn Turn 5 state');
      assert.strictEqual(sent.state.progression.energy, 80, 'pre-turn energy must be sent untouched');
      assert.strictEqual(res.outcome.next_state.turn, 6);
      assert.strictEqual(res.outcome.next_state.progression.energy, 70);
      assert.ok(res.narration.text.includes('Unseal the brine-stained harbor ledger'));

      // Also test when outcome.next_state.turn differs from explicit currentTurn
      const skewedOutcome = Core.resolve(preState, '1', turn5Config);
      skewedOutcome.next_state.turn = 9;
      await localNarrator.generateNarrative({
        action: '1',
        outcome: skewedOutcome,
        state: preState,
        endpoint: 'http://localhost:8000/generate',
        campaign: 'harbor_chronicle',
        currentTurn: 5
      });
      assert.strictEqual(calls[1].body.currentTurn, 5, 'explicit currentTurn must override derived fallback');
    } finally {
      global.fetch = originalFetch;
    }
  });

  await t.test('Generic local endpoint excludes Whimsy-specific keys and browser credentials unless intended', async () => {
    const calls = [];
    global.fetch = async (url, init) => {
      calls.push({ url, headers: init.headers, body: JSON.parse(init.body) });
      return {
        ok: true,
        json: async () => ({
          choices: [{ message: { content: 'Cold harbor fog drifts across the ledger.\n\n[OPTIONS]\n1. Unseal the brine-stained harbor ledger' } }]
        })
      };
    };

    try {
      const preState = buildTurn5State();
      const outcome = Core.resolve(preState, '1', turn5Config);
      await localNarrator.generateNarrative({
        action: '1',
        outcome,
        state: preState,
        context: { genre: 'Maritime Noir', activeConfig: { id: 'harbor_chronicle' } },
        endpoint: 'http://localhost:11434/v1/chat/completions',
        campaign: 'harbor_chronicle',
        currentTurn: 5,
        apiKey: 'sk-or-browser-secret',
        provider: 'openrouter',
        model: 'openrouter/anthropic/claude-3.5-sonnet',
        apiBaseUrl: 'https://openrouter.ai/api/v1/chat/completions',
        pacing: 'standard',
        commit: true
      });

      assert.strictEqual(calls.length, 1);
      const { headers, body } = calls[0];
      assert.strictEqual(headers.Authorization, undefined);
      for (const forbidden of ['action', 'outcome', 'context', 'campaign', 'currentTurn', 'state', 'pacing', 'commit', 'apiKey', 'provider', 'apiBaseUrl']) {
        assert.strictEqual(forbidden in body, false, `generic local endpoint must not receive '${forbidden}'`);
      }
      assert.ok(Array.isArray(body.messages) && body.messages.length === 1);
      assert.strictEqual('model' in body, false, 'cloud-prefixed model should not be sent to generic local endpoint');
    } finally {
      global.fetch = originalFetch;
    }
  });
});

test('Browser Runtime - Service Worker restricts caching strictly to same-origin static assets', () => {
  const vm = require('vm');
  const swPath = path.resolve(__dirname, '../UI/sw.js');
  const swCode = fs.readFileSync(swPath, 'utf8');
  const listeners = {};
  const ctx = {
    URL,
    self: {
      location: { href: 'http://localhost:3000/sw.js', origin: 'http://localhost:3000' },
      addEventListener: (ev, fn) => { listeners[ev] = fn; },
      skipWaiting: () => {},
      clients: { claim: () => {} }
    },
    caches: {
      open: async () => ({ addAll: async () => {}, put: async () => {} }),
      match: async () => null,
      keys: async () => [],
      delete: async () => {}
    },
    fetch: async () => ({ status: 200, type: 'basic', clone: () => ({}) })
  };
  vm.createContext(ctx);
  vm.runInContext(swCode, ctx);

  assert.strictEqual(typeof listeners.fetch, 'function');
  const makeEvent = (url, method = 'GET') => {
    let responded = false;
    listeners.fetch({
      request: { url, method, mode: 'cors', headers: { get: () => '' } },
      respondWith: () => { responded = true; }
    });
    return responded;
  };

  assert.strictEqual(makeEvent('http://localhost:3000/index.html', 'GET'), true);
  assert.strictEqual(makeEvent('http://localhost:3000/app.js', 'GET'), true);
  assert.strictEqual(makeEvent('http://localhost:3000/api/campaign?campaign=private_camp', 'GET'), false);
  assert.strictEqual(makeEvent('http://localhost:3000/api/campaigns', 'GET'), false);
  assert.strictEqual(makeEvent('http://localhost:8000/index.html', 'GET'), false, 'cross-origin must not be intercepted');
  assert.strictEqual(makeEvent('http://localhost:3000/generate', 'POST'), false);
});
