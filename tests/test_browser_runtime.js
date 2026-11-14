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
