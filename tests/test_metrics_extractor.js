/**
 * tests/test_metrics_extractor.js
 * Unit tests for top bar metrics extraction in UI/app.js.
 * Tests structured JSON extraction, priority handling, and regex text fallbacks:
 * - Strain Buffer parsing
 * - Multi-denomination purse formatting ("0 Platinum, 3 Gold Crowns, 6 Silver Marks, 20 Copper Cogs" -> "3G 6S 20C")
 * - Backtick coin parsing (`3G 6S 20C`)
 * - Alternate-schema custom metrics (Divinity, Faith, Authority)
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const test = require('node:test');
const assert = require('node:assert');

function setupTestEnvironment() {
  const appPath = path.resolve(__dirname, '../UI/app.js');
  const code = fs.readFileSync(appPath, 'utf8');

  // Virtual DOM elements store
  const domElements = new Map();

  function getOrCreateElement(id) {
    if (!domElements.has(id)) {
      domElements.set(id, {
        id,
        textContent: '',
        style: {},
        innerHTML: '',
        addEventListener: () => {}
      });
    }
    return domElements.get(id);
  }

  const context = {
    window: {},
    navigator: {},
    document: {
      getElementById: (id) => getOrCreateElement(id),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: (tag) => ({ tag, style: {}, addEventListener: () => {} })
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    console: { log: () => {}, error: () => {}, warn: () => {} },
    setTimeout: () => {},
    clearTimeout: () => {}
  };

  vm.createContext(context);
  vm.runInContext(code, context);

  return {
    context,
    domElements,
    getElementText: (id) => domElements.get(id)?.textContent ?? '',
    setActiveConfig: (config) => {
      vm.runInContext(`activeConfig = ${JSON.stringify(config)};`, context);
    },
    extractMetrics: (statusText, itemsText, statusJson) => {
      context.testArgs = { statusText, itemsText, statusJson };
      return vm.runInContext('extractMetrics(testArgs.statusText, testArgs.itemsText, testArgs.statusJson)', context);
    }
  };
}

const primaryConfig = {
  id: 'template_campaign',
  metrics: [
    { id: 'turn', label: 'Turn', type: 'counter', path: 'turn' },
    { id: 'xp', label: 'XP', type: 'progress', path: 'progression.xp', max_path: 'progression.xp_threshold', regex: 'XP:\\s*(\\d+)\\s*\\/\\s*(\\d+)', max: 500 },
    { id: 'strain', label: 'Strain', type: 'progress', path: 'progression.mana_strain', max_path: 'progression.strain_max', regex: 'Strain(?:\\s*Buffer)?:\\s*([0-9\\/]+)', max: 10 },
    { id: 'purse', label: 'Purse', type: 'text', path: 'purse.display', regex: '(?:Current Coin\\*?:\\s*`([^`]+)`|Currency Purse\\*?:\\s*\\*\\*([^*]+)\\*\\*)' }
  ]
};

const templateConfig = {
  id: 'template_campaign',
  metrics: [
    { id: 'turn', label: 'Turn', type: 'counter', path: 'turn' },
    { id: 'energy', label: 'Energy', type: 'progress', color: '#58a6ff', path: 'progression.energy', max_path: 'progression.energy_max' },
    { id: 'stress', label: 'Stress', type: 'progress', color: '#f85149', path: 'progression.stress', max_path: 'progression.stress_max' },
    { id: 'funds', label: 'Funds', type: 'text', path: 'purse.display' }
  ]
};

const cosmicConfig = {
  id: 'sample_campaign',
  metrics: [
    { id: 'turn', label: 'Cycle', type: 'counter', path: 'turn' },
    { id: 'divinity', label: 'Divinity', type: 'progress', path: 'progression.divinity', max_path: 'progression.divinity_max', regex: 'Divinity:\\s*(\\d+)\\s*\\/\\s*(\\d+)' },
    { id: 'faith', label: 'Faith Pool', type: 'progress', path: 'progression.faith_pool', regex: 'Faith:\\s*(\\d+)' },
    { id: 'authority', label: 'Authority', type: 'text', path: 'progression.divine_authority', regex: 'Divine Authority:\\s*(\\d+)' }
  ]
};

test('Metrics Extractor - Structured JSON (Highest Precedence)', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(primaryConfig);

  const statusJson = {
    turn: 246,
    progression: {
      xp: 330,
      xp_threshold: 500,
      mana_strain: 2,
      strain_max: 10
    },
    purse: {
      display: '4G 2S 10C',
      gold: 4,
      silver: 2,
      copper: 10
    }
  };

  // Provide conflicting markdown text to ensure JSON wins
  const markdownStatus = 'Turn: 100\nXP: 50 / 500\nStrain: 0/10';
  const markdownItems = 'Current Coin: `1G 0S 0C`';

  env.extractMetrics(markdownStatus, markdownItems, statusJson);

  assert.strictEqual(env.getElementText('val-turn'), 246);
  assert.strictEqual(env.getElementText('val-xp'), '330 / 500');
  assert.strictEqual(env.getElementText('val-strain'), '2 / 10');
  assert.strictEqual(env.getElementText('val-purse'), '4G 2S 10C');
});

test('Metrics Extractor - Structured JSON purse breakdown fallback', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(primaryConfig);

  const statusJson = {
    turn: 245,
    progression: { xp: 315, xp_threshold: 500, mana_strain: 0, strain_max: 10 },
    purse: {
      // display is missing; must compute from gold/silver/copper
      gold: 5,
      silver: 12,
      copper: 50
    }
  };

  env.extractMetrics('', '', statusJson);
  assert.strictEqual(env.getElementText('val-purse'), '5G 12S 50C');
});

test('Metrics Extractor - Markdown Text Fallbacks (Regex)', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(primaryConfig);

  const markdownStatus = `
# TEMPLATE CAMPAIGN — STATUS
* **Turn**: **245** (Active Sync: Turn 244 Concluded)
* **Progression**: Level 3 Peak Initiate | **XP: 315 / 500** (185 XP to Breakthrough).
* **Vitals**: Mana Pool: 100% | **Strain Buffer: 0 / 10** (Completely Rested).
* **Currency Purse**: **0 Platinum, 3 Gold Crowns, 6 Silver Marks, 20 Copper Cogs**.
`;
  const markdownItems = `
# INVENTORY
* **Current Coin**: \`3G 6S 20C\`
`;

  // statusJson is null -> triggers regex path
  env.extractMetrics(markdownStatus, markdownItems, null);

  assert.strictEqual(env.getElementText('val-turn'), 245);
  assert.strictEqual(env.getElementText('val-xp'), '315 / 500');
  assert.strictEqual(env.getElementText('val-strain'), '0 / 10');
  // Backtick current coin match
  assert.strictEqual(env.getElementText('val-purse'), '3G 6S 20C');
});

test('Metrics Extractor - Multi-denomination purse verbal regex formatting', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(primaryConfig);

  // When only Currency Purse prose exists (no backtick Current Coin)
  const markdownStatus = `
* **Turn**: 120
* **XP: 200 / 500**
* Strain: 3/10
* Currency Purse: **0 Platinum, 12 Gold Crowns, 5 Silver Marks, 80 Copper Cogs**
`;

  env.extractMetrics(markdownStatus, '', null);

  // Should normalize "0 Platinum, 12 Gold Crowns, 5 Silver Marks, 80 Copper Cogs" into "12G 5S 80C"
  assert.strictEqual(env.getElementText('val-purse'), '12G 5S 80C');
  assert.strictEqual(env.getElementText('val-strain'), '3 / 10');
});

test('Metrics Extractor - Alternative Genre Campaign (Custom Schema)', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(cosmicConfig);

  const customStatusJson = {
    turn: 1,
    progression: {
      divinity: 95,
      divinity_max: 100,
      faith_pool: 50,
      divine_authority: 13
    }
  };

  env.extractMetrics('', '', customStatusJson);

  assert.strictEqual(env.getElementText('val-turn'), 1);
  assert.strictEqual(env.getElementText('val-divinity'), '95 / 100');
  assert.strictEqual(env.getElementText('val-faith'), 50);
  assert.strictEqual(env.getElementText('val-authority'), 13);
});

test('Metrics Extractor - Alternative Genre Regex Fallbacks', () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(cosmicConfig);

  const customText = `
# Cycle 2
* Divinity: 98 / 100
* Faith: 75
* Divine Authority: 15
`;

  env.extractMetrics(customText, '', null);

  assert.strictEqual(env.getElementText('val-turn'), 2);
  assert.strictEqual(env.getElementText('val-divinity'), '98 / 100');
  assert.strictEqual(env.getElementText('val-faith'), '75');
  assert.strictEqual(env.getElementText('val-authority'), '15');
});

test('Metrics Extractor - schema-driven SYS updateAfterTurn', async () => {
  const env = setupTestEnvironment();
  env.setActiveConfig(templateConfig);

  vm.runInContext(`
    currentTurn = 1;
    campaignData.statusJson = {
      turn: 1,
      progression: { energy: 100, energy_max: 100, stress: 10, stress_max: 100 },
      purse: { display: '500 credits' }
    };
  `, env.context);

  await vm.runInContext(
    'updateAndPersistState("[SYS: Turn 2 | Energy 80/100 | Stress 25/100 | Funds: 400 credits]")',
    env.context
  );

  assert.strictEqual(env.getElementText('val-turn'), 2);
  assert.strictEqual(env.getElementText('val-energy'), '80 / 100');
  assert.strictEqual(env.getElementText('val-stress'), '25 / 100');
  assert.strictEqual(env.getElementText('val-funds'), '400 credits');
});
