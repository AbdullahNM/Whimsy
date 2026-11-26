const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '../UI/app.js'), 'utf8');

for (const [campaignId, savedId] of [
  ['template_campaign', null],
  ['demo_campaign', 'unavailable_campaign']
]) {
  test(`Startup hydrates the bundled ${campaignId}`, async () => {
    function createElement() {
      return {
        children: [],
        style: {},
        dataset: {},
        addEventListener() {},
        querySelector: () => null,
        appendChild(child) { this.children.push(child); }
      };
    }

    const elements = new Map();
    const getElementById = (id) => {
      if (!elements.has(id)) elements.set(id, createElement());
      return elements.get(id);
    };
    const campaignSelect = getElementById('campaign-select');
    campaignSelect.value = 'template_campaign';

    const errors = [];
    vm.runInNewContext(appSource, {
      window: {
        __INLINED_BUILD__: true,
        __BUNDLED_CAMPAIGN_ID__: campaignId,
        __WORLD_BIBLE_DATA__: {},
        __CAMPAIGN_CONFIGS__: { [campaignId]: { title: 'Test Campaign' } },
        __GAMEPLAY_MANIFEST__: {
          [campaignId]: { status_json: { turn: 1, scene_anchor: { context: 'The ferry is waiting.' } } }
        }
      },
      navigator: {},
      document: { getElementById, createElement, querySelector: () => null, querySelectorAll: () => [] },
      localStorage: { getItem: (key) => key === 'cyoa_selected_campaign' ? savedId : null },
      console: { error: (...args) => errors.push(args.map(String).join(' ')), warn() {} },
      setTimeout() {},
      clearTimeout() {}
    });

    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(errors, []);
    assert.equal(campaignSelect.value, campaignId);
    assert.match(getElementById('story-stream').children[0]?.innerHTML ?? '', /The ferry is waiting\./);
  });
}
