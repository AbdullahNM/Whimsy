/**
 * tests/test_markdown_parser.js
 * Unit tests for Markdown parser in UI/app.js.
 * Tests non-greedy bold/italics, code block isolation, task checkboxes, and semantic lists.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const test = require('node:test');
const assert = require('node:assert');

// Load UI/app.js functions in isolated context
function loadAppFunctions() {
  const appPath = path.resolve(__dirname, '../UI/app.js');
  const code = fs.readFileSync(appPath, 'utf8');

  const context = {
    window: {},
    navigator: {},
    document: {
      getElementById: (id) => ({ id, textContent: '', style: {}, addEventListener: () => {} }),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({ style: {}, addEventListener: () => {} })
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
    parseInlineMarkdown: context.parseInlineMarkdown,
    renderMarkdown: context.renderMarkdown,
    splitTurnNarrativeAndReceipts: context.splitTurnNarrativeAndReceipts
  };
}

const { parseInlineMarkdown, renderMarkdown, splitTurnNarrativeAndReceipts } = loadAppFunctions();

test('Markdown Parser - Non-greedy bold and italics', () => {
  // Test multiple bold segments on one line
  const boldText = '**First Bold** and some regular text and **Second Bold**';
  const inlineBold = parseInlineMarkdown(boldText);
  assert.ok(inlineBold.includes('<strong>First Bold</strong>'));
  assert.ok(inlineBold.includes('<strong>Second Bold</strong>'));
  assert.ok(!inlineBold.includes('<strong>First Bold** and some regular text and **Second Bold</strong>'));

  // Test multiple italics segments
  const italicText = '*First Italic* between *Second Italic*';
  const inlineItalic = parseInlineMarkdown(italicText);
  assert.ok(inlineItalic.includes('<em>First Italic</em>'));
  assert.ok(inlineItalic.includes('<em>Second Italic</em>'));

  // Test underscore bold and italics
  const underBold = '__Underscore Bold__ text';
  assert.ok(parseInlineMarkdown(underBold).includes('<strong>Underscore Bold</strong>'));

  const underItalic = 'some _Underscore Italic_ word';
  assert.ok(parseInlineMarkdown(underItalic).includes('<em>Underscore Italic</em>'));

  // Test inline code
  const codeText = 'Use `const x = 10;` here';
  assert.ok(parseInlineMarkdown(codeText).includes('<code class="inline-code">const x = 10;</code>'));
});

test('Markdown Parser - Code block isolation and preservation', () => {
  const textWithCode = `
Here is a code block:
\`\`\`json
{
  "turn": 245,
  "xp": "**not bold**",
  "comment": "<script>alert(1)</script>"
}
\`\`\`
Followed by **bold paragraph**.
`;

  const rendered = renderMarkdown(textWithCode);

  // Must contain pre and code elements
  assert.ok(rendered.includes('<pre class="code-block"><code class="lang-json">'));
  assert.ok(rendered.includes('</code></pre>'));

  // Markdown inside code block must NOT be parsed into strong tags
  assert.ok(!rendered.includes('<code><strong>not bold</strong></code>'));
  assert.ok(rendered.includes('&quot;**not bold**&quot;') || rendered.includes('"**not bold**"'));

  // HTML inside code block must be escaped
  assert.ok(rendered.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));

  // Regular paragraph after code block IS parsed
  assert.ok(rendered.includes('<strong>bold paragraph</strong>'));
});

test('Markdown Parser - Task list checkboxes', () => {
  const listText = `
- [ ] Incomplete task item
- [x] Completed task item
* [X] Another completed task item
`;

  const rendered = renderMarkdown(listText);

  assert.ok(rendered.includes('<ul class="task-list">'));
  assert.ok(rendered.includes('<span class="task-box">☐</span> Incomplete task item'));
  assert.ok(rendered.includes('<span class="task-box checked">☑</span> Completed task item'));
  assert.ok(rendered.includes('<span class="task-box checked">☑</span> Another completed task item'));
});

test('Markdown Parser - Semantic lists (ordered & unordered)', () => {
  const unorderedText = `
* First bullet
* Second bullet
- Third bullet
`;

  const renderedUl = renderMarkdown(unorderedText);
  assert.ok(renderedUl.includes('<ul>'));
  assert.ok(renderedUl.includes('<li>First bullet</li>'));
  assert.ok(renderedUl.includes('<li>Second bullet</li>'));
  assert.ok(renderedUl.includes('<li>Third bullet</li>'));
  assert.ok(renderedUl.includes('</ul>'));

  const orderedText = `
1. First step
2. Second step
3. Third step
`;

  const renderedOl = renderMarkdown(orderedText);
  assert.ok(renderedOl.includes('<ol>'));
  assert.ok(renderedOl.includes('<li>First step</li>'));
  assert.ok(renderedOl.includes('<li>Second step</li>'));
  assert.ok(renderedOl.includes('<li>Third step</li>'));
  assert.ok(renderedOl.includes('</ol>'));
});

test('Markdown Parser - Headers, blockquotes, and dividers', () => {
  const doc = `
# Title 1
## Subtitle 2
### Section 3
#### Heading 4
> This is a wise quote.
---
Regular paragraph text.
`;

  const rendered = renderMarkdown(doc);

  assert.ok(rendered.includes('<h1>Title 1</h1>'));
  assert.ok(rendered.includes('<h2>Subtitle 2</h2>'));
  assert.ok(rendered.includes('<h3>Section 3</h3>'));
  assert.ok(rendered.includes('<h4>Heading 4</h4>'));
  assert.ok(rendered.includes('<blockquote>This is a wise quote.</blockquote>'));
  assert.ok(rendered.includes('<hr class="divider">'));
  assert.ok(rendered.includes('<p>Regular paragraph text.</p>'));
});

test('Markdown Parser - Delimited receipt blocks', () => {
  const receiptText = `
Spar ended.
[XP RESOLUTION: Previous: 315 | Delta: +15 | New Total: 330 / 500]
[CURRENCY RESOLUTION: Previous: 3G 6S 20C | Delta: 0 | New Purse: 3G 6S 20C]
[SYS: Turn 246 | Strain 0/10]
`;

  const rendered = renderMarkdown(receiptText);

  assert.ok(rendered.includes('<div class="receipt-block"><span class="receipt-tag">[XP RESOLUTION:'));
  assert.ok(rendered.includes('<div class="receipt-block"><span class="receipt-tag">[CURRENCY RESOLUTION:'));
  assert.ok(rendered.includes('<div class="receipt-block sys-block"><span class="receipt-tag">[SYS:'));
});

test('Clean Narrative Viewport - splitTurnNarrativeAndReceipts', () => {
  const rawTurn = `
# Turn 244

## GM Response
Down in the pit, the provost's whistle shrills across the cold breeze.

---

[OPTIONS & TYPABLE REFERENCE]
1. Head over to the central mess hall with the crew to grab lunch.
2. Go down into the ring to talk with the training staff.
3. Walk back to the library steps to find the research team.

[SYS: Turn 244 | Lvl 3 | XP 315/500 | Purse: 3G 6S 20C | Strain: 0/10 | Active RECAL: Macro pacing, simple English - Expires: Turn 246]
`;

  const { cleanNarrative, receipts, optionsText } = splitTurnNarrativeAndReceipts(rawTurn);

  // Clean narrative must NOT contain [OPTIONS] or [SYS:]
  assert.ok(!cleanNarrative.includes('[OPTIONS & TYPABLE REFERENCE]'));
  assert.ok(!cleanNarrative.includes('[SYS:'));
  assert.ok(!cleanNarrative.includes('Head over to the central mess hall'));
  assert.ok(cleanNarrative.includes("the provost's whistle shrills across the cold breeze."));

  // Receipts must be extracted
  assert.equal(receipts.length, 1);
  assert.ok(receipts[0].includes('Turn 244'));
  assert.ok(receipts[0].includes('Active RECAL: Macro pacing'));

  // Options text must be extracted
  assert.ok(optionsText.includes('Head over to the central mess hall'));
  assert.ok(optionsText.includes('Go down into the ring'));
});
