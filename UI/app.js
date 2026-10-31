let dirHandle = null;
let currentTurn = 0;
let selectedChoice = null;
let campaignConfigs = {};
let activeConfig = null;
let gameplayManifest = {};

// View Mode States for Sidebar Tabs
let currentStatusView = 'hud'; // 'hud' or 'markdown'
let currentRelationsView = 'cards'; // 'cards' or 'markdown'
let currentItemsView = 'cards'; // 'cards' or 'markdown'
let currentOntologyView = 'graph'; // 'graph' or 'markdown'

let campaignData = {
  status: '',
  relations: '',
  items: '',
  statusJson: null,
  relationsJson: null,
  itemsJson: null,
  ontologyJson: null,
  narrativeSteering: '',
  upcomingHooks: '',
  activeTurns: []
};

// Register Service Worker for PWA / Mobile Install
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js')
      .then(reg => console.log('PWA ServiceWorker registered:', reg.scope))
      .catch(err => console.log('ServiceWorker registration skipped:', err));
  });
}

// Helpers
function getNestedValue(obj, path) {
  if (!obj || !path) return undefined;
  return path.split('.').reduce((prev, curr) => (prev && prev[curr] !== undefined) ? prev[curr] : undefined, obj);
}

function setNestedValue(obj, path, value) {
  if (!obj || !path) return false;
  const parts = path.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    if (typeof node[key] !== 'object' || node[key] === null) node[key] = {};
    node = node[key];
  }
  node[parts[parts.length - 1]] = value;
  return true;
}

function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Robust, non-greedy Markdown parser
function parseInlineMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+?)__/g, '<strong>$1</strong>')
    .replace(/(^|[^\*])\*([^\*]+?)\*([^\*]|$)/g, '$1<em>$2</em>$3')
    .replace(/(^|[^_])_([^_]+?)_([^_]|$)/g, '$1<em>$2</em>$3');
}

function renderMarkdown(text) {
  if (!text) return '';

  // 1. Extract and preserve code blocks (``` ... ```)
  const codeBlocks = [];
  let processed = text.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/gim, (match, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre class="code-block"><code class="lang-${lang}">${escapeHtml(code.trim())}</code></pre>`);
    return `%%CODEBLOCK_${idx}%%`;
  });

  // 2. Extract and format receipts & system blocks
  processed = processed
    .replace(/\[(XP RESOLUTION:[\s\S]*?)\]/gi, '<div class="receipt-block"><span class="receipt-tag">[$1]</span></div>')
    .replace(/\[(CURRENCY RESOLUTION:[\s\S]*?)\]/gi, '<div class="receipt-block"><span class="receipt-tag">[$1]</span></div>')
    .replace(/\[(SYS:[\s\S]*?)\]/gi, '<div class="receipt-block sys-block"><span class="receipt-tag">[$1]</span></div>');

  // 3. Process line-by-line block elements
  const lines = processed.split('\n');
  const outputLines = [];
  let inUl = false;
  let inOl = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Horizontal rule: --- or === or ***
    if (/^(\s*[-*_]){3,}\s*$/.test(line) || /^={10,}\s*$/.test(line)) {
      if (inUl) { outputLines.push('</ul>'); inUl = false; }
      if (inOl) { outputLines.push('</ol>'); inOl = false; }
      outputLines.push('<hr class="divider">');
      continue;
    }

    // Headers
    if (/^#### (.*$)/.test(line)) {
      if (inUl) { outputLines.push('</ul>'); inUl = false; }
      if (inOl) { outputLines.push('</ol>'); inOl = false; }
      outputLines.push(`<h4>${parseInlineMarkdown(line.replace(/^#### /, ''))}</h4>`);
      continue;
    }
    if (/^### (.*$)/.test(line)) {
      if (inUl) { outputLines.push('</ul>'); inUl = false; }
      if (inOl) { outputLines.push('</ol>'); inOl = false; }
      outputLines.push(`<h3>${parseInlineMarkdown(line.replace(/^### /, ''))}</h3>`);
      continue;
    }
    if (/^## (.*$)/.test(line)) {
      if (inUl) { outputLines.push('</ul>'); inUl = false; }
      if (inOl) { outputLines.push('</ol>'); inOl = false; }
      outputLines.push(`<h2>${parseInlineMarkdown(line.replace(/^## /, ''))}</h2>`);
      continue;
    }
    if (/^# (.*$)/.test(line)) {
      if (inUl) { outputLines.push('</ul>'); inUl = false; }
      if (inOl) { outputLines.push('</ol>'); inOl = false; }
      outputLines.push(`<h1>${parseInlineMarkdown(line.replace(/^# /, ''))}</h1>`);
      continue;
    }

    // Sub-item task list check item (indented):   - [X] or   - [ ]
    const subCheckMatch = line.match(/^(\s+|\t+)[-*]\s*\[([ xX])\]\s*(.*)/);
    if (subCheckMatch) {
      if (!inUl) { outputLines.push('<ul class="task-list">'); inUl = true; }
      const isChecked = subCheckMatch[2].toLowerCase() === 'x';
      const checkIcon = isChecked ? '<span class="task-box checked">☑</span>' : '<span class="task-box">☐</span>';
      outputLines.push(`<li class="task-item sub-item">${checkIcon} ${parseInlineMarkdown(subCheckMatch[3])}</li>`);
      continue;
    }

    // Sub-item unordered list item (indented):   - or   *
    const subUlMatch = line.match(/^(\s+|\t+)[-*]\s+(.*)/);
    if (subUlMatch) {
      if (!inUl) { outputLines.push('<ul>'); inUl = true; }
      outputLines.push(`<li class="sub-item">${parseInlineMarkdown(subUlMatch[2])}</li>`);
      continue;
    }

    // Sub-item ordered list item (indented):   1. or 1)
    const subOlMatch = line.match(/^(\s+|\t+)(\d+)[\.\)]\s+(.*)/);
    if (subOlMatch) {
      if (!inOl) { outputLines.push('<ol>'); inOl = true; }
      outputLines.push(`<li class="sub-item ordered-sub-item">${parseInlineMarkdown(subOlMatch[3])}</li>`);
      continue;
    }

    // Top-level Task list check item: - [X] or - [ ]
    const checkMatch = line.match(/^[-*]\s*\[([ xX])\]\s*(.*)/);
    if (checkMatch) {
      if (!inUl) { outputLines.push('<ul class="task-list">'); inUl = true; }
      const isChecked = checkMatch[1].toLowerCase() === 'x';
      const checkIcon = isChecked ? '<span class="task-box checked">☑</span>' : '<span class="task-box">☐</span>';
      outputLines.push(`<li class="task-item">${checkIcon} ${parseInlineMarkdown(checkMatch[2])}</li>`);
      continue;
    }

    // Top-level Unordered list item: * or -
    const ulMatch = line.match(/^[-*]\s+(.*)/);
    if (ulMatch) {
      if (!inUl) { outputLines.push('<ul>'); inUl = true; }
      outputLines.push(`<li>${parseInlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }

    // Top-level Ordered list item: 1. or 1)
    const olMatch = line.match(/^(\d+)[\.\)]\s+(.*)/);
    if (olMatch) {
      if (!inOl) { outputLines.push('<ol>'); inOl = true; }
      outputLines.push(`<li>${parseInlineMarkdown(olMatch[2])}</li>`);
      continue;
    }

    // Close open lists on non-list lines
    if (inUl) { outputLines.push('</ul>'); inUl = false; }
    if (inOl) { outputLines.push('</ol>'); inOl = false; }

    // Blockquote: >
    if (/^>\s*(.*)/.test(line)) {
      outputLines.push(`<blockquote>${parseInlineMarkdown(line.replace(/^>\s*/, ''))}</blockquote>`);
      continue;
    }

    // Codeblock placeholder or empty line
    if (line.includes('%%CODEBLOCK_')) {
      outputLines.push(line);
      continue;
    }

    if (!line.trim()) {
      continue;
    }

    outputLines.push(`<p>${parseInlineMarkdown(line)}</p>`);
  }

  if (inUl) outputLines.push('</ul>');
  if (inOl) outputLines.push('</ol>');

  let result = outputLines.join('\n');

  // Restore preserved code blocks
  codeBlocks.forEach((cb, idx) => {
    result = result.replace(`%%CODEBLOCK_${idx}%%`, cb);
  });

  return result;
}

const renderSimpleMarkdown = renderMarkdown; // Compatibility alias

// DOM Elements
const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
const expandSidebarBtn = document.getElementById('expand-sidebar-btn');
const sidebar = document.getElementById('sidebar');
const folderPickerBtn = document.getElementById('folder-picker-btn');
const syncStatus = document.getElementById('sync-status');
const topMetricsContainer = document.getElementById('top-metrics-container');
const storyStream = document.getElementById('story-stream');
const choiceGrid = document.getElementById('choice-buttons-container');
const recalInput = document.getElementById('recal-input');
const submitActionBtn = document.getElementById('submit-action-btn');
const campaignSelect = document.getElementById('campaign-select');

// IndexedDB Directory Handle Persistence
const DB_NAME = 'CYOA_ENGINE_DB';
const DB_VERSION = 1;
const STORE_NAME = 'handles';

function openHandleDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveStoredHandle(handle) {
  try {
    const db = await openHandleDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(handle, 'workspace_dir');
  } catch (e) {
    console.warn('Could not store handle in IndexedDB:', e);
  }
}

async function getStoredHandle() {
  try {
    const db = await openHandleDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).get('workspace_dir');
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
  } catch (e) {
    return null;
  }
}

// Load Campaign Configs & Initial Gameplay Data
async function loadInitialData() {
  try {
    const [confRes, gameRes] = await Promise.all([
      fetch('campaign_configs.json'),
      fetch('gameplay_manifest.json')
    ]);
    campaignConfigs = await confRes.json();
    gameplayManifest = await gameRes.json();

    // 1. Populate campaign dropdown dynamically from loaded configs
    if (campaignSelect) {
      const savedCampaign = localStorage.getItem('cyoa_selected_campaign');
      const targetVal = (savedCampaign && campaignConfigs[savedCampaign]) 
        ? savedCampaign 
        : (campaignSelect.value || Object.keys(campaignConfigs)[0]);
      
      campaignSelect.innerHTML = '';
      Object.keys(campaignConfigs).forEach(id => {
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = (campaignConfigs[id].title || id).toUpperCase();
        if (id === targetVal) opt.selected = true;
        campaignSelect.appendChild(opt);
      });
      campaignSelect.value = targetVal;
    }

    applyActiveCampaignConfig();
    loadManifestDataIntoUI();

    // Check for existing stored folder handle
    const storedHandle = await getStoredHandle();
    if (storedHandle) {
      dirHandle = storedHandle;
      try {
        let perm = await storedHandle.queryPermission({ mode: 'readwrite' });
        if (perm !== 'granted') {
          perm = await storedHandle.queryPermission({ mode: 'read' });
        }
        if (perm === 'granted') {
          syncStatus.textContent = storedHandle.name;
          syncStatus.className = 'status-pill status-connected';
          syncStatus.title = 'Workspace connected';
          await loadWorkspace(storedHandle);
        } else {
          syncStatus.textContent = `⚡ Reconnect: ${storedHandle.name}`;
          syncStatus.className = 'status-pill status-reconnect';
          syncStatus.title = 'Click to re-authorize workspace folder access';
        }
      } catch (err) {
        syncStatus.textContent = `⚡ Reconnect: ${storedHandle.name}`;
        syncStatus.className = 'status-pill status-reconnect';
        syncStatus.title = 'Click to re-authorize workspace folder access';
      }
    }
  } catch (e) {
    console.error('Failed to load initial configs/manifest:', e);
  }
}

async function attemptReconnect(handle) {
  if (!handle) return false;
  try {
    const perm = await handle.requestPermission({ mode: 'readwrite' });
    if (perm === 'granted') {
      dirHandle = handle;
      syncStatus.textContent = handle.name;
      syncStatus.className = 'status-pill status-connected';
      syncStatus.title = 'Workspace connected';
      await loadWorkspace(handle);
      return true;
    } else {
      syncStatus.textContent = `⚡ Reconnect: ${handle.name}`;
      syncStatus.className = 'status-pill status-reconnect';
    }
  } catch (e) {
    console.warn('Reconnect error:', e);
  }
  return false;
}

// One-click Reconnection on sync-status pill
syncStatus.addEventListener('click', async () => {
  if (dirHandle) {
    await attemptReconnect(dirHandle);
  }
});

function renderInitialCampaignScene(campaignId) {
  storyStream.innerHTML = '';
  const conf = campaignConfigs[campaignId] || {};
  const statusJson = campaignData.statusJson;
  const loc = statusJson?.scene_anchor?.location || 'Unknown Coordinates';
  const ctx = statusJson?.scene_anchor?.context || 'Awaiting initial action.';
  const time = statusJson?.scene_anchor?.time || '';

  const card = document.createElement('div');
  card.className = 'scene-card welcome-card';
  card.innerHTML = `
    <div class="turn-header">${escapeHtml(conf.title || campaignId).toUpperCase()} • PROLOGUE</div>
    <h2>${escapeHtml(conf.genre || 'New Campaign Adventure')}</h2>
    <p><strong>Coordinates:</strong> ${escapeHtml(loc)}</p>
    <p>${escapeHtml(ctx)}</p>
    ${time ? `<div style="font-size:11px; color:var(--gold-primary); margin-top:6px;">⏱ ${escapeHtml(time)}</div>` : ''}
  `;
  storyStream.appendChild(card);

  if (campaignData.upcomingHooks) {
    parseAndRenderNewChoices(`[OPTIONS]\n${campaignData.upcomingHooks}`);
  }
}

function loadManifestDataIntoUI() {
  const selectedId = campaignSelect ? campaignSelect.value : '';
  const campData = gameplayManifest[selectedId];
  if (!campData) return;

  campaignData.status = campData.status || '';
  campaignData.relations = campData.relations || '';
  campaignData.items = campData.items || '';
  campaignData.statusJson = campData.status_json || null;
  campaignData.relationsJson = campData.relations_json || null;
  campaignData.itemsJson = campData.items_json || null;
  campaignData.ontologyJson = campData.ontology_json || null;
  campaignData.narrativeSteering = campData.narrative_steering || '';
  campaignData.upcomingHooks = campData.upcoming_hooks || '';

  // Reset active turns and populate from manifest
  campaignData.activeTurns = campData.active_turns ? JSON.parse(JSON.stringify(campData.active_turns)) : [];
  currentTurnViewIndex = -1;

  renderSchemaDrivenStatus(campaignData.statusJson, activeConfig, campData.status);
  renderRelations(campaignData.relationsJson, campData.relations);
  renderItems(campaignData.itemsJson, campData.items);
  if (campaignData.ontologyJson) {
    renderOntology(campaignData.ontologyJson);
  }
  renderIdeas(campaignData.narrativeSteering, campaignData.upcomingHooks);
  extractMetrics(campData.status, campData.items, campaignData.statusJson);

  if (campaignData.activeTurns.length > 0) {
    renderStoryStream(campaignData.activeTurns);
  } else {
    renderInitialCampaignScene(selectedId);
  }
}

loadInitialData();

function applyActiveCampaignConfig() {
  const selectedId = campaignSelect ? campaignSelect.value : '';
  activeConfig = campaignConfigs[selectedId];
  if (!activeConfig) return;

  // 1. Apply Dynamic CSS Theme Variables
  if (activeConfig.theme) {
    const root = document.documentElement;
    const t = activeConfig.theme;
    if (t.bg_dark) root.style.setProperty('--bg-dark', t.bg_dark);
    if (t.bg_slate) root.style.setProperty('--bg-slate', t.bg_slate);
    if (t.bg_card) root.style.setProperty('--bg-card', t.bg_card);
    if (t.gold_primary) root.style.setProperty('--gold-primary', t.gold_primary);
    if (t.gold_dim) root.style.setProperty('--gold-dim', t.gold_dim);
    if (t.accent_glow) root.style.setProperty('--gold-glow', t.accent_glow);
    if (t.text_ivory) root.style.setProperty('--text-ivory', t.text_ivory);
    if (t.font_family) document.body.style.fontFamily = t.font_family;
  }

  // 2. Render Dynamic Top Bar Metrics from Schema
  if (topMetricsContainer && activeConfig.metrics) {
    topMetricsContainer.innerHTML = '';
    activeConfig.metrics.forEach(m => {
      const pill = document.createElement('span');
      pill.className = 'metric-pill';
      pill.id = `metric-pill-${m.id}`;
      pill.innerHTML = `${m.label}: <strong id="val-${m.id}">—</strong>`;
      topMetricsContainer.appendChild(pill);
    });
  }

  // 3. Render Dynamic Sidebar Tabs from Schema
  if (activeConfig.sidebar && activeConfig.sidebar.tabs) {
    const tabsContainer = document.querySelector('.sidebar-tabs');
    if (tabsContainer) {
      tabsContainer.innerHTML = '';
      activeConfig.sidebar.tabs.forEach((tab, idx) => {
        const btn = document.createElement('button');
        btn.className = idx === 0 ? 'tab-btn active' : 'tab-btn';
        btn.dataset.tab = tab.id;
        btn.textContent = tab.label;
        btn.addEventListener('click', () => {
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          const target = document.getElementById(tab.id);
          if (target) target.classList.add('active');
        });
        tabsContainer.appendChild(btn);
      });

      // Ensure the first tab pane is active
      const firstTab = activeConfig.sidebar.tabs[0];
      if (firstTab) {
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        const target = document.getElementById(firstTab.id);
        if (target) target.classList.add('active');
      }
    }
  }

  // 4. Render Dynamic Schema-Driven Status Card
  if (campaignData.statusJson || campaignData.status) {
    renderSchemaDrivenStatus(campaignData.statusJson, activeConfig, campaignData.status);
  }
  if (campaignData.relationsJson || campaignData.relations) {
    renderRelations(campaignData.relationsJson, campaignData.relations);
  }
  if (campaignData.itemsJson || campaignData.items) {
    renderItems(campaignData.itemsJson, campaignData.items);
  }
  if (campaignData.ontologyJson) {
    renderOntology(campaignData.ontologyJson);
  }

  // 5. Render Dynamic Arcs & Steering
  renderIdeas(campaignData.narrativeSteering, campaignData.upcomingHooks);

  // 6. Update top bar metrics from active campaign state
  extractMetrics(campaignData.status, campaignData.items, campaignData.statusJson);
}

// 1. Schema-Driven Status Renderer (HUD Card vs Markdown View)
function renderSchemaDrivenStatus(statusJson, config, markdownFallback = '') {
  const statusContainer = document.getElementById('status-render');
  if (!statusContainer) return;

  if (!statusJson || !config || !config.entity_header) {
    if (markdownFallback) {
      statusContainer.innerHTML = renderMarkdown(markdownFallback);
    }
    return;
  }

  let html = `
    <div class="status-view-toggle">
      <button class="toggle-view-btn ${currentStatusView === 'hud' ? 'active' : ''}" id="btn-view-hud">📊 HUD Card</button>
      <button class="toggle-view-btn ${currentStatusView === 'markdown' ? 'active' : ''}" id="btn-view-md">📜 Living Record</button>
    </div>
  `;

  if (currentStatusView === 'markdown') {
    html += `<div class="status-markdown-view">${renderMarkdown(markdownFallback || campaignData.status || '')}</div>`;
    statusContainer.innerHTML = html;
    attachStatusToggleListeners(statusJson, config, markdownFallback);
    return;
  }

  // Entity Badge Header
  const title = getNestedValue(statusJson, config.entity_header.title_path) || 'Active Entity';
  const subtitle = getNestedValue(statusJson, config.entity_header.subtitle_path) || '';
  const tags = (config.entity_header.tag_paths || [])
    .map(p => getNestedValue(statusJson, p))
    .filter(Boolean);

  html += `
    <div class="status-badge-card">
      <div class="badge-title">${escapeHtml(title)}</div>
      ${subtitle ? `<div class="badge-subtitle">${escapeHtml(subtitle)}</div>` : ''}
      <div class="badge-tags">
        ${tags.map(t => `<span class="tag">${escapeHtml(String(t))}</span>`).join('')}
      </div>
    </div>
  `;

  const sections = config.status_sections || {};

  // Progression Bars
  if (sections.progression_bars && sections.progression_bars.bars) {
    html += `
      <div class="accordion-section">
        <div class="accordion-header active">${escapeHtml(sections.progression_bars.title || 'Progression')}</div>
        <div class="accordion-body">
    `;
    sections.progression_bars.bars.forEach(bar => {
      const val = getNestedValue(statusJson, bar.path) ?? 0;
      const maxVal = bar.max_path ? (getNestedValue(statusJson, bar.max_path) ?? 100) : 100;
      const pct = Math.max(0, Math.min(100, Math.round((val / maxVal) * 100)));
      html += `
        <div class="stat-bar-group">
          <div class="stat-bar-label">
            <span>${escapeHtml(bar.label)}</span>
            <span><strong>${val}</strong> / ${maxVal} ${bar.unit || ''}</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" style="width: ${pct}%; background-color: ${bar.color || 'var(--gold-primary)'};"></div>
          </div>
        </div>
      `;
    });
    html += `</div></div>`;
  }

  // Stat Grid Boxes
  if (sections.stat_grid && sections.stat_grid.boxes) {
    html += `
      <div class="accordion-section">
        <div class="accordion-header">${escapeHtml(sections.stat_grid.title || 'Counters & Vitals')}</div>
        <div class="accordion-body">
          <div class="stat-grid">
    `;
    sections.stat_grid.boxes.forEach(box => {
      const val = getNestedValue(statusJson, box.path);
      if (val !== undefined && val !== null) {
        html += `
          <div class="stat-box">
            <span class="lbl">${escapeHtml(box.label)}</span>
            <span class="val">${escapeHtml(String(val))} ${box.suffix || ''}</span>
          </div>
        `;
      }
    });
    html += `</div></div></div>`;
  }

  // Attributes / Aptitudes Grid
  if (sections.attributes_grid && sections.attributes_grid.dict_path) {
    const dict = getNestedValue(statusJson, sections.attributes_grid.dict_path);
    if (dict && typeof dict === 'object') {
      const maxScale = sections.attributes_grid.max_scale || 100;
      html += `
        <div class="accordion-section">
          <div class="accordion-header">${escapeHtml(sections.attributes_grid.title || 'Aptitudes & Attributes')}</div>
          <div class="accordion-body">
            <ul class="clean-stat-list">
      `;
      for (const [k, v] of Object.entries(dict)) {
        const formattedKey = k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        html += `<li><span>${escapeHtml(formattedKey)}:</span> <strong>${v}/${maxScale}</strong></li>`;
      }
      html += `</ul></div></div>`;
    }
  }

  // Inventory / Catalysts Status
  if (sections.inventory_status && sections.inventory_status.array_path) {
    const arr = getNestedValue(statusJson, sections.inventory_status.array_path);
    if (Array.isArray(arr) && arr.length > 0) {
      const nameKey = sections.inventory_status.item_name_key || 'name';
      const statusKey = sections.inventory_status.item_status_key || 'secured';
      const locKey = sections.inventory_status.item_location_key || 'location';
      html += `
        <div class="accordion-section">
          <div class="accordion-header">${escapeHtml(sections.inventory_status.title || 'Sacred Relics & Catalysts')}</div>
          <div class="accordion-body">
            <ul class="clean-stat-list" style="grid-template-columns: 1fr;">
      `;
      arr.forEach(item => {
        const check = item[statusKey] ? '☑' : '☐';
        const loc = item[locKey] ? ` <em style="color:var(--text-muted); font-size:11px;">(${escapeHtml(item[locKey])})</em>` : '';
        html += `<li><span>${check} ${escapeHtml(item[nameKey] || '')}</span>${loc}</li>`;
      });
      html += `</ul></div></div>`;
    }
  }

  // Scene Anchor
  if (sections.scene_anchor) {
    const loc = getNestedValue(statusJson, sections.scene_anchor.location_path);
    const ctx = getNestedValue(statusJson, sections.scene_anchor.context_path);
    const time = getNestedValue(statusJson, sections.scene_anchor.time_path);
    if (loc || ctx || time) {
      html += `
        <div class="accordion-section">
          <div class="accordion-header">${escapeHtml(sections.scene_anchor.title || 'Scene Anchor')}</div>
          <div class="accordion-body">
            ${loc ? `<p style="margin:0; font-size:12px; color:var(--text-ivory);"><strong>Coordinates:</strong> ${escapeHtml(loc)}</p>` : ''}
            ${ctx ? `<p style="margin:4px 0 0 0; font-size:12px; color:var(--text-muted); line-height:1.4;">${escapeHtml(ctx)}</p>` : ''}
            ${time ? `<div style="font-size:11px; color:var(--gold-primary); margin-top:4px;">⏱ ${escapeHtml(time)}</div>` : ''}
          </div>
        </div>
      `;
    }
  }

  statusContainer.innerHTML = html;
  attachStatusToggleListeners(statusJson, config, markdownFallback);
}

function attachStatusToggleListeners(statusJson, config, markdownFallback) {
  const btnHud = document.getElementById('btn-view-hud');
  const btnMd = document.getElementById('btn-view-md');
  if (btnHud) {
    btnHud.addEventListener('click', () => {
      currentStatusView = 'hud';
      renderSchemaDrivenStatus(statusJson, config, markdownFallback);
    });
  }
  if (btnMd) {
    btnMd.addEventListener('click', () => {
      currentStatusView = 'markdown';
      renderSchemaDrivenStatus(statusJson, config, markdownFallback);
    });
  }
}

// 2. Structured Relations Renderer
function renderRelations(relationsJson, markdownFallback = '') {
  const container = document.getElementById('relations-render');
  if (!container) return;

  if (!relationsJson) {
    container.innerHTML = renderMarkdown(markdownFallback || campaignData.relations || '');
    return;
  }

  let html = `
    <div class="status-view-toggle">
      <button class="toggle-view-btn ${currentRelationsView === 'cards' ? 'active' : ''}" id="btn-rel-cards">👥 Companion & Faction Cards</button>
      <button class="toggle-view-btn ${currentRelationsView === 'markdown' ? 'active' : ''}" id="btn-rel-md">📜 Living Registry</button>
    </div>
  `;

  if (currentRelationsView === 'markdown') {
    html += `<div class="status-markdown-view">${renderMarkdown(markdownFallback || campaignData.relations || '')}</div>`;
    container.innerHTML = html;
    attachRelationsToggleListeners(relationsJson, markdownFallback);
    return;
  }

  // Dynamic Generic Category Loop for ANY campaign genre (Teen Romance, Sci-Fi, Mystery, Fantasy, etc.)
  const knownRelKeys = ['campaign_id'];
  for (const [key, val] of Object.entries(relationsJson)) {
    if (knownRelKeys.includes(key)) continue;
    if (Array.isArray(val) && val.length > 0) {
      const groupTitle = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      html += `<div class="accordion-header active" style="margin:12px 0 8px 0; border-radius:4px;">${escapeHtml(groupTitle)}</div>`;
      val.forEach(item => {
        let accentClass = 'close';
        const keyLower = key.toLowerCase();
        if (keyLower.includes('rival') || keyLower.includes('threat') || keyLower.includes('faction') || keyLower.includes('suspect') || keyLower.includes('warning')) {
          accentClass = 'warning';
        } else if (keyLower.includes('mentor') || keyLower.includes('faculty') || keyLower.includes('informant') || keyLower.includes('witness')) {
          accentClass = 'mentor';
        }

        const name = item.name || item.title || 'Contact';
        const status = item.status || item.disposition || item.threat_level || item.standing || (item.threat_level ? 'Threat: ' + item.threat_level : 'Active');
        const subtitle = item.division || item.role || item.archetype || item.affiliation || item.alibi || '';
        const standing = item.standing ? `<strong>Standing:</strong> ${escapeHtml(String(item.standing))}` : '';
        const notes = item.notes || item.details || item.desc || item.disposition || '';

        html += `
          <div class="relation-card ${accentClass}">
            <div class="rel-name">
              <span>${escapeHtml(name)}</span>
              <span class="rel-tag">${escapeHtml(String(status))}</span>
            </div>
            ${subtitle ? `<div style="font-size:11px; color:var(--gold-primary); margin-bottom:4px;">${escapeHtml(subtitle)}</div>` : ''}
            ${standing ? `<div style="font-size:11px; color:var(--accent-cyan); margin-bottom:6px;">${standing}</div>` : ''}
            ${notes ? `<div class="rel-desc">${escapeHtml(notes)}</div>` : ''}
          </div>
        `;
      });
    }
  }

  container.innerHTML = html;
  attachRelationsToggleListeners(relationsJson, markdownFallback);
}

function attachRelationsToggleListeners(relationsJson, markdownFallback) {
  const btnCards = document.getElementById('btn-rel-cards');
  const btnMd = document.getElementById('btn-rel-md');
  if (btnCards) {
    btnCards.addEventListener('click', () => {
      currentRelationsView = 'cards';
      renderRelations(relationsJson, markdownFallback);
    });
  }
  if (btnMd) {
    btnMd.addEventListener('click', () => {
      currentRelationsView = 'markdown';
      renderRelations(relationsJson, markdownFallback);
    });
  }
}

// 3. Structured Items / Inventory Renderer (Genre-Agnostic)
function renderItems(itemsJson, markdownFallback = '') {
  const container = document.getElementById('items-render');
  if (!container) return;

  if (!itemsJson) {
    container.innerHTML = renderMarkdown(markdownFallback || campaignData.items || '');
    return;
  }

  let html = `
    <div class="status-view-toggle">
      <button class="toggle-view-btn ${currentItemsView === 'cards' ? 'active' : ''}" id="btn-items-cards">🎒 Inventory Cards</button>
      <button class="toggle-view-btn ${currentItemsView === 'markdown' ? 'active' : ''}" id="btn-items-md">📜 Living Ledger</button>
    </div>
  `;

  if (currentItemsView === 'markdown') {
    html += `<div class="status-markdown-view">${renderMarkdown(markdownFallback || campaignData.items || '')}</div>`;
    container.innerHTML = html;
    attachItemsToggleListeners(itemsJson, markdownFallback);
    return;
  }

  // Currency / Wealth Ledger (if purse exists)
  if (itemsJson.purse) {
    const p = itemsJson.purse;
    html += `
      <div class="accordion-header active" style="margin-bottom:8px; border-radius:4px;">Currency / Wealth Ledger (${escapeHtml(p.display || '')})</div>
    `;
    if (p.gold !== undefined || p.platinum !== undefined) {
      html += `
        <div class="coin-grid">
          <div class="coin-box plat"><div class="coin-num">${p.platinum || 0}</div><div class="coin-denom">Platinum</div></div>
          <div class="coin-box gold"><div class="coin-num">${p.gold || 0}</div><div class="coin-denom">Gold</div></div>
          <div class="coin-box silver"><div class="coin-num">${p.silver || 0}</div><div class="coin-denom">Silver</div></div>
          <div class="coin-box copper"><div class="coin-num">${p.copper || 0}</div><div class="coin-denom">Copper</div></div>
        </div>
      `;
    } else {
      html += `
        <div class="stat-box" style="margin-bottom:10px;">
          <span class="lbl">Current Balance</span>
          <span class="val">${escapeHtml(p.display || String(p.credits || p.dollars || p.funds || p.cash || 0))}</span>
        </div>
      `;
    }
  }

  // Dynamic Array Sections (Equipped, Clues, Cyberware, Documents, Keepsakes, Evidence, Relics)
  const knownItemKeys = ['campaign_id', 'purse'];
  for (const [key, val] of Object.entries(itemsJson)) {
    if (knownItemKeys.includes(key)) continue;
    if (Array.isArray(val) && val.length > 0) {
      const sectionTitle = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      html += `<div class="accordion-header" style="margin:12px 0 8px 0; border-radius:4px;">${escapeHtml(sectionTitle)}</div>`;
      val.forEach(item => {
        const title = item.name || item.title || 'Item';
        let tag = item.slot || item.type || item.status || item.condition || 'Active';
        if (item.secured !== undefined) {
          tag = item.secured ? '☑ Secured' : '☐ Missing';
        }
        const specs = item.specs || item.details || item.grants || item.notes || item.desc || '';
        const loc = item.location ? `Location: <strong>${escapeHtml(item.location)}</strong>` : '';

        html += `
          <div class="item-card">
            <div class="item-card-header">
              <span class="item-card-title">${escapeHtml(title)}</span>
              <span class="tag">${escapeHtml(String(tag))}</span>
            </div>
            ${loc || specs ? `<div class="item-card-desc">${loc ? loc + ' | ' : ''}${escapeHtml(specs)}</div>` : ''}
          </div>
        `;
      });
    }
  }

  container.innerHTML = html;
  attachItemsToggleListeners(itemsJson, markdownFallback);
}

function attachItemsToggleListeners(itemsJson, markdownFallback) {
  const btnCards = document.getElementById('btn-items-cards');
  const btnMd = document.getElementById('btn-items-md');
  if (btnCards) {
    btnCards.addEventListener('click', () => {
      currentItemsView = 'cards';
      renderItems(itemsJson, markdownFallback);
    });
  }
  if (btnMd) {
    btnMd.addEventListener('click', () => {
      currentItemsView = 'markdown';
      renderItems(itemsJson, markdownFallback);
    });
  }
}

// 4. Structured Ontology & Lineage Graph Renderer
let activeOntologyFilter = 'all';

function renderOntology(ontologyJson, markdownFallback = '') {
  const container = document.getElementById('ontology-render');
  if (!container) return;

  if (!ontologyJson) {
    container.innerHTML = renderMarkdown(markdownFallback || '<p class=\"hint\">No lineage ontology loaded.</p>');
    return;
  }

  let html = `
    <div class=\"status-view-toggle\">
      <button class=\"toggle-view-btn ${currentOntologyView === 'graph' ? 'active' : ''}\" id=\"btn-ont-graph\">🌳 Knowledge Graph & Trees</button>
      <button class=\"toggle-view-btn ${currentOntologyView === 'markdown' ? 'active' : ''}\" id=\"btn-ont-md\">📜 Living House Lore</button>
    </div>
  `;

  if (currentOntologyView === 'markdown') {
    html += `<div class=\"status-markdown-view\">${renderMarkdown(markdownFallback || '### Prominent Houses & Lineages\n*Refer to WORLD_BIBLE/FACTIONS/prominent_houses_and_clans.md for comprehensive prose histories.*')}</div>`;
    container.innerHTML = html;
    attachOntologyToggleListeners(ontologyJson, markdownFallback);
    return;
  }

  // Filter Pills
  html += `
    <div class=\"lore-pills\" style=\"margin-bottom:12px;\">
      <button class=\"lore-pill ${activeOntologyFilter === 'all' ? 'active' : ''}\" data-ont-filter=\"all\">All</button>
      <button class=\"lore-pill ${activeOntologyFilter === 'guardrails' ? 'active' : ''}\" data-ont-filter=\"guardrails\">Guardrails</button>
      <button class=\"lore-pill ${activeOntologyFilter === 'cohorts' ? 'active' : ''}\" data-ont-filter=\"cohorts\">Cohorts</button>
      <button class=\"lore-pill ${activeOntologyFilter === 'houses' ? 'active' : ''}\" data-ont-filter=\"houses\">Great Houses</button>
      <button class=\"lore-pill ${activeOntologyFilter === 'edges' ? 'active' : ''}\" data-ont-filter=\"edges\">Kinship & Edges</button>
    </div>
  `;

  // 1. Mandatory Disambiguation Guardrails
  if ((activeOntologyFilter === 'all' || activeOntologyFilter === 'guardrails') && ontologyJson.disambiguation_rules) {
    html += `<div class=\"accordion-header active\" style=\"margin:12px 0 8px 0; border-radius:4px;\">🛡️ Disambiguation Guardrails (Anti-Collision)</div>`;
    ontologyJson.disambiguation_rules.forEach(rule => {
      html += `
        <div class=\"relation-card warning\" style=\"margin-bottom:8px;\">
          <div class=\"rel-name\">
            <span>${escapeHtml(rule.rule_id.replace('RULE_', ''))}</span>
            <span class=\"rel-tag\" style=\"background:rgba(239, 68, 68, 0.2); color:#f87171;\">Strict Guardrail</span>
          </div>
          <div style=\"font-size:11px; color:#fca5a5; margin:4px 0;\">${escapeHtml(rule.confusion_risk)}</div>
          <div class=\"rel-desc\" style=\"color:var(--text-ivory); font-weight:500;\"><strong>Guidance:</strong> ${escapeHtml(rule.operational_guardrail)}</div>
        </div>
      `;
    });
  }

  // 2. Cohort Rosters
  if ((activeOntologyFilter === 'all' || activeOntologyFilter === 'cohorts') && ontologyJson.cohort_rosters) {
    html += `<div class=\"accordion-header active\" style=\"margin:12px 0 8px 0; border-radius:4px;\">⚔️ Academy Cohorts & Doctrines</div>`;
    const chars = ontologyJson.characters || {};
    for (const [cId, cohort] of Object.entries(ontologyJson.cohort_rosters)) {
      const memberNames = (cohort.members || []).map(mId => {
        const c = chars[mId];
        return c ? c.name : mId;
      }).join(', ');

      html += `
        <div class=\"relation-card close\" style=\"margin-bottom:8px;\">
          <div class=\"rel-name\">
            <span>${escapeHtml(cohort.cohort_name)}</span>
            <span class=\"rel-tag\">${escapeHtml(cohort.division ? cohort.division.split('(')[0].trim() : 'Cohort')}</span>
          </div>
          <div style=\"font-size:11px; color:var(--gold-primary); margin:4px 0;\"><strong>Doctrine:</strong> ${escapeHtml(cohort.tactical_doctrine || '')}</div>
          <div class=\"rel-desc\"><strong>Roster:</strong> ${escapeHtml(memberNames)}</div>
        </div>
      `;
    }
  }

  // 3. Great Houses & Lineages
  if ((activeOntologyFilter === 'all' || activeOntologyFilter === 'houses') && ontologyJson.houses_and_lineages) {
    html += `<div class=\"accordion-header active\" style=\"margin:12px 0 8px 0; border-radius:4px;\">🏰 Great Houses & Lineages</div>`;
    for (const [hId, house] of Object.entries(ontologyJson.houses_and_lineages)) {
      html += `
        <div class=\"relation-card mentor\" style=\"margin-bottom:8px;\">
          <div class=\"rel-name\">
            <span>${escapeHtml(house.house_name)}</span>
            <span class=\"rel-tag\">${escapeHtml(house.status_tier || 'House')}</span>
          </div>
          <div style=\"font-size:11px; color:var(--gold-primary); margin:2px 0;\"><em>\"${escapeHtml(house.motto || '')}\"</em></div>
          <div style=\"font-size:11px; color:var(--text-dim); margin-bottom:4px;\"><strong>Seat:</strong> ${escapeHtml(house.seat_or_territory || 'Unassigned')}</div>
          <div class=\"rel-desc\">${escapeHtml(house.ancestral_rite || '')}</div>
        </div>
      `;
    }
  }

  // 4. Relational Graph Edges
  if ((activeOntologyFilter === 'all' || activeOntologyFilter === 'edges') && ontologyJson.relational_graph_edges) {
    html += `<div class=\"accordion-header active\" style=\"margin:12px 0 8px 0; border-radius:4px;\">🔗 Key Relational Graph Edges</div>`;
    const chars = ontologyJson.characters || {};
    ontologyJson.relational_graph_edges.forEach(edge => {
      const srcName = chars[edge.source] ? chars[edge.source].name : edge.source;
      const tgtName = chars[edge.target] ? chars[edge.target].name : edge.target;
      const relType = edge.type ? edge.type.replace(/_/g, ' ').toUpperCase() : 'BOND';

      let edgeClass = '';
      if (edge.type.includes('kinship')) edgeClass = 'close';
      else if (edge.type.includes('rival') || edge.type.includes('enmity')) edgeClass = 'warning';
      else if (edge.type.includes('mentor')) edgeClass = 'mentor';

      html += `
        <div class=\"relation-card ${edgeClass}\" style=\"margin-bottom:6px;\">
          <div class=\"rel-name\">
            <span>${escapeHtml(srcName)} ➔ ${escapeHtml(tgtName)}</span>
            <span class=\"rel-tag\">${escapeHtml(relType)}</span>
          </div>
          <div class=\"rel-desc\">${escapeHtml(edge.description || '')}</div>
        </div>
      `;
    });
  }

  container.innerHTML = html;
  attachOntologyToggleListeners(ontologyJson, markdownFallback);
}

function attachOntologyToggleListeners(ontologyJson, markdownFallback) {
  const btnGraph = document.getElementById('btn-ont-graph');
  const btnMd = document.getElementById('btn-ont-md');
  if (btnGraph) {
    btnGraph.addEventListener('click', () => {
      currentOntologyView = 'graph';
      renderOntology(ontologyJson, markdownFallback);
    });
  }
  if (btnMd) {
    btnMd.addEventListener('click', () => {
      currentOntologyView = 'markdown';
      renderOntology(ontologyJson, markdownFallback);
    });
  }

  // Filter pills
  document.querySelectorAll('[data-ont-filter]').forEach(pill => {
    pill.addEventListener('click', () => {
      activeOntologyFilter = pill.dataset.ontFilter;
      renderOntology(ontologyJson, markdownFallback);
    });
  });
}

// 5. Dynamic Arcs & Steering Renderer
function renderIdeas(narrativeSteering = '', upcomingHooks = '') {
  const container = document.getElementById('ideas-render');
  if (!container) return;

  let combined = '';
  if (narrativeSteering) {
    combined += narrativeSteering.trim() + '\n\n';
  }
  if (upcomingHooks) {
    if (combined && !upcomingHooks.trim().startsWith('#')) {
      combined += '### Upcoming Hooks & Leads\n';
    }
    combined += upcomingHooks.trim();
  }

  if (combined.trim()) {
    container.innerHTML = renderMarkdown(combined);
  } else {
    container.innerHTML = '<p class="hint">No narrative steering or arc notes recorded for this campaign.</p>';
  }
}

// Pacing & Settings
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeSettingsBtn = document.getElementById('close-settings-btn');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const apiKeyInput = document.getElementById('gemini-api-key');
const pacingSelect = document.getElementById('pacing-select');
const modelSelect = document.getElementById('gemini-model-select');
const maxTurnsInput = document.getElementById('max-turns-input');
const localEndpointInput = document.getElementById('local-endpoint-url');
const localEndpointGroup = document.getElementById('local-endpoint-group');

// Load stored settings
if (localStorage.getItem('gemini_api_key')) {
  apiKeyInput.value = localStorage.getItem('gemini_api_key');
}
if (localStorage.getItem('cyoa_pacing')) {
  pacingSelect.value = localStorage.getItem('cyoa_pacing');
}
if (localStorage.getItem('cyoa_model') && modelSelect) {
  modelSelect.value = localStorage.getItem('cyoa_model');
}
if (localStorage.getItem('cyoa_local_endpoint') && localEndpointInput) {
  localEndpointInput.value = localStorage.getItem('cyoa_local_endpoint');
}
if (localStorage.getItem('cyoa_max_turns') && maxTurnsInput) {
  maxTurnsInput.value = localStorage.getItem('cyoa_max_turns');
}

function updateModelSettingsVisibility() {
  if (!modelSelect || !localEndpointGroup) return;
  const isLocal = modelSelect.value === 'local-antigravity' || modelSelect.value === 'local-endpoint';
  localEndpointGroup.style.display = isLocal ? 'block' : 'none';
}
if (modelSelect) {
  modelSelect.addEventListener('change', updateModelSettingsVisibility);
  updateModelSettingsVisibility();
}

settingsBtn.addEventListener('click', () => {
  updateModelSettingsVisibility();
  settingsModal.classList.remove('hidden');
});
closeSettingsBtn.addEventListener('click', () => settingsModal.classList.add('hidden'));
saveSettingsBtn.addEventListener('click', () => {
  localStorage.setItem('gemini_api_key', apiKeyInput.value.trim());
  localStorage.setItem('cyoa_pacing', pacingSelect.value);
  if (modelSelect) {
    localStorage.setItem('cyoa_model', modelSelect.value);
  }
  if (localEndpointInput) {
    localStorage.setItem('cyoa_local_endpoint', localEndpointInput.value.trim());
  }
  if (maxTurnsInput) {
    localStorage.setItem('cyoa_max_turns', maxTurnsInput.value);
  }
  settingsModal.classList.add('hidden');
});

// Campaign Switching
if (campaignSelect) {
  campaignSelect.addEventListener('change', () => {
    localStorage.setItem('cyoa_selected_campaign', campaignSelect.value);
    applyActiveCampaignConfig();
    loadManifestDataIntoUI();
    if (dirHandle) {
      loadWorkspace(dirHandle);
    }
  });
}

// Sidebar Controls: Toggle & Expand
toggleSidebarBtn.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
});

expandSidebarBtn.addEventListener('click', () => {
  sidebar.classList.toggle('expanded');
  expandSidebarBtn.textContent = sidebar.classList.contains('expanded') ? '⤡' : '⤢';
});

// World Bible Data & Browser Logic
let worldBibleData = null;
const loreCategorySelect = document.getElementById('lore-category-select');
const loreArticleList = document.getElementById('lore-article-list');
const loreArticleContent = document.getElementById('lore-article-content');

async function initWorldBible() {
  try {
    const res = await fetch('world_bible_data.json');
    worldBibleData = await res.json();
    populateLoreCategories();
    if (loreCategorySelect && loreCategorySelect.value) {
      renderWorldBibleCategory(loreCategorySelect.value);
    }
  } catch (err) {
    console.error('Failed to load world bible data:', err);
    if (loreArticleContent) {
      loreArticleContent.innerHTML = '<p style="color:var(--accent-crimson)">Failed to load World Bible manifest.</p>';
    }
  }
}

const LORE_CATEGORY_LABELS = {
  CORE: 'CORE (Rules & Systems)',
  PLACES: 'PLACES (Locations & Architecture)',
  PEOPLE: 'PEOPLE (Characters)',
  FACTIONS: 'FACTIONS (Organisations & Powers)',
  GUIDES: 'GUIDES (Turn Rules & Schemas)'
};

// Only offer categories that actually contain articles in world_bible_data.json.
function populateLoreCategories() {
  if (!loreCategorySelect || !worldBibleData) return;

  const available = Object.keys(worldBibleData).filter(k => Array.isArray(worldBibleData[k]) && worldBibleData[k].length > 0);
  if (available.length === 0) return;

  const preferred = ['CORE', 'PLACES', 'PEOPLE', 'FACTIONS', 'GUIDES'];
  available.sort((a, b) => {
    const ia = preferred.indexOf(a);
    const ib = preferred.indexOf(b);
    return (ia === -1 ? preferred.length : ia) - (ib === -1 ? preferred.length : ib) || a.localeCompare(b);
  });

  const previous = loreCategorySelect.value;
  loreCategorySelect.innerHTML = '';
  available.forEach(key => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = LORE_CATEGORY_LABELS[key] || key.toUpperCase();
    loreCategorySelect.appendChild(opt);
  });
  loreCategorySelect.value = available.includes(previous) ? previous : available[0];
}

if (loreCategorySelect) {
  loreCategorySelect.addEventListener('change', () => {
    if (worldBibleData) {
      renderWorldBibleCategory(loreCategorySelect.value);
    }
  });
}

function renderWorldBibleCategory(category) {
  if (!worldBibleData || !worldBibleData[category]) {
    loreArticleList.innerHTML = '<p class="text-muted">No articles found in this category.</p>';
    loreArticleContent.innerHTML = '';
    return;
  }

  const articles = worldBibleData[category];
  loreArticleList.innerHTML = '';

  articles.forEach((art, idx) => {
    const pill = document.createElement('button');
    pill.className = idx === 0 ? 'lore-pill active' : 'lore-pill';
    pill.textContent = art.title;
    pill.addEventListener('click', () => {
      document.querySelectorAll('.lore-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      renderArticleContent(art);
    });
    loreArticleList.appendChild(pill);
  });

  if (articles.length > 0) {
    renderArticleContent(articles[0]);
  }
}

function renderArticleContent(article) {
  loreArticleContent.innerHTML = `
    <div class="article-header">
      <h3>${article.title}</h3>
      <span class="article-id">${article.id}.md</span>
    </div>
    <div class="article-body">
      ${renderMarkdown(article.content)}
    </div>
  `;
}

initWorldBible();
setupChoiceButtonListeners();

function setupChoiceButtonListeners() {
  document.querySelectorAll('.choice-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedChoice = {
        num: btn.dataset.choice,
        text: btn.querySelector('.choice-desc').textContent.trim()
      };
      recalInput.focus();
    });
  });
}

// Submit Action Button (Choice + RECAL)
submitActionBtn.addEventListener('click', () => {
  if (!selectedChoice) {
    alert("Please select one of the numbered choices first (or pick an action).");
    return;
  }
  executeTurnAction(selectedChoice.num, selectedChoice.text);
});

async function executeTurnAction(choiceNum, choiceText) {
  const resolvingTurn = currentTurn;
  const recal = recalInput.value.trim();
  const playerAction = recal ? `${choiceNum}. ${choiceText} [RECAL: ${recal}]` : `${choiceNum}. ${choiceText}`;
  recalInput.value = '';

  // Render Player action card
  appendCard(`Turn ${resolvingTurn} • Player Action`, `<p><strong>${escapeHtml(playerAction)}</strong></p>`, true);

  // Show thinking indicator
  const loadingBody = appendCard(`Turn ${resolvingTurn} • Game Master`, '<p><em>Simulating world response and calculating matrix causalities...</em></p>');

  const selectedModel = modelSelect ? modelSelect.value : (localStorage.getItem('cyoa_model') || 'local-antigravity');
  const isLocal = selectedModel === 'local-antigravity' || selectedModel === 'local-endpoint';
  const apiKey = localStorage.getItem('gemini_api_key');

  if (!isLocal && !apiKey) {
    loadingBody.innerHTML = `<p style="color: var(--accent-crimson)"><strong>Error:</strong> No Gemini API Key configured for cloud model. Click ⚙ in the top bar to set your key, or select <strong>Local Antigravity</strong>.</p>`;
    return;
  }

  try {
    const pacing = localStorage.getItem('cyoa_pacing') || 'standard';
    const response = await callGeminiAPI(apiKey, playerAction, pacing);

    // Format full turn file content with standard Turn / Player Action / GM Response headers
    const turnFileName = `turn_${String(resolvingTurn).padStart(4, '0')}.md`;
    const fullTurnContent = `# Turn ${resolvingTurn}\n\n## Player Action\n${playerAction}\n\n## GM Response\n${response}\n`;

    campaignData.activeTurns = campaignData.activeTurns || [];
    campaignData.activeTurns.push({ name: turnFileName, content: fullTurnContent });
    currentTurnViewIndex = campaignData.activeTurns.length - 1;
    renderCurrentTurnView(campaignData.activeTurns);

    // Parse and persist state deltas (XP, coin, strain) to disk & memory
    await updateAndPersistState(response);

    // Save turn file to disk if workspace is connected
    if (dirHandle) {
      await saveTurnToDisk(resolvingTurn, playerAction, response);
    }

    // Now advance currentTurn to the next pending turn
    currentTurn = resolvingTurn + 1;
    const turnEl = document.getElementById('val-turn');
    if (turnEl) turnEl.textContent = currentTurn;

    // Update status.json and status.md with currentTurn
    if (campaignData.statusJson) {
      campaignData.statusJson.turn = currentTurn;
    }
    if (campaignData.status) {
      campaignData.status = campaignData.status.replace(/Turn\*?:\s*\*?\d+\*?/i, `Turn**: **${currentTurn}**`);
    }

    parseAndRenderNewChoices(response);
  } catch (err) {
    loadingBody.innerHTML = `<p style="color: var(--accent-crimson)"><strong>Generation Error:</strong> ${escapeHtml(err.message)}</p>`;
  }
}

async function callGeminiAPI(apiKey, playerAction, pacing) {
  const model = modelSelect ? modelSelect.value : (localStorage.getItem('cyoa_model') || 'local-antigravity');
  const campaignTitle = activeConfig ? activeConfig.title : 'CYOA RPG';
  const selectedCampaign = campaignSelect ? campaignSelect.value : '';

  let pacingGuideline = "Write exactly 2 to 3 balanced paragraphs of vivid, high-sensory narrative.";
  if (pacing === 'concise') {
    pacingGuideline = "Write exactly 1 to 2 short, punchy paragraphs. Keep scene transition tight and crisp.";
  } else if (pacing === 'expansive') {
    pacingGuideline = "Write 3 to 4 immersive, atmospheric paragraphs with rich NPC dialogue and environmental detail.";
  }

  // 1. Local Engine / Antigravity Dispatch
  if (model === 'local-antigravity' || model === 'local-endpoint') {
    const endpoint = (localEndpointInput && localEndpointInput.value.trim()) || localStorage.getItem('cyoa_local_endpoint') || 'http://localhost:8000/generate';
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: playerAction,
          pacing: pacing,
          campaign: selectedCampaign,
          currentTurn: currentTurn,
          state: campaignData.statusJson || campaignData.status,
          relations: campaignData.relationsJson || campaignData.relations,
          items: campaignData.itemsJson || campaignData.items,
          pacingGuideline: pacingGuideline,
          apiKey: apiKey || ''
        })
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Local engine returned HTTP ${res.status}: ${errText}`);
      }
      const data = await res.json();
      return data.response || data.text || data.candidates?.[0]?.content?.parts?.[0]?.text || data.choices?.[0]?.message?.content || JSON.stringify(data);
    } catch (err) {
      throw new Error(`Local Antigravity engine is not responding at ${endpoint}.\n\n• To run locally: run \`python3 ENGINE/engine.py\` in your terminal\n• Or switch to Gemini 2.5 Flash / Pro in Settings (⚙).`);
    }
  }

  // 2. Cloud Gemini API Dispatch
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  // Build dynamic system instruction using loaded GAMEPLAY files
  const dynamicState = `
# AUTHORITATIVE LIVING STATE (GAMEPLAY):
${campaignData.status || (campaignData.statusJson ? JSON.stringify(campaignData.statusJson, null, 2) : "Active Scene Anchor loaded")}

# SOCIAL STANDING & RELATIONSHIPS:
${campaignData.relations || "Allies and mentors active"}

# INVENTORY & ASSETS:
${campaignData.items || "Equipped gear and regalia intact"}
`;

  const trackedMetrics = (activeConfig && activeConfig.metrics || [])
    .map(m => `${m.label}${m.max_path ? ' (current / max)' : ''}`)
    .join(', ') || 'narrative milestones only';

  const payload = {
    contents: [
      {
        role: "user",
        parts: [{ text: `Player Action: ${playerAction}` }]
      }
    ],
    systemInstruction: {
      parts: [{
        text: `You are the Game Master for the ${campaignTitle} CYOA RPG.
${dynamicState}

Tracked values: ${trackedMetrics}.

Formatting & Pacing Rules (CORE-002 & CORE-003):
1. ${pacingGuideline} Lead with physical choreography and grounded sensory details.
2. Provide proactive living NPC initiative.
3. Conclude with 3 to 6 actionable numbered choices (e.g. "1. [Action text]").
4. Proactive Receipts: If a tracked value shifts, append one exact line:
   [PROGRESSION/RESOURCE RESOLUTION: Previous: X | Delta: ±Y (Reason) | New Total: Z]
5. Always finish with the system block:
   [SYS: Turn ${currentTurn + 1} | <tracked values> | Checkpoints: <C>/5]`
      }]
    }
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data.error?.message || 'API request failed');
  return data.candidates[0].content.parts[0].text;
}

async function updateAndPersistState(text) {
  let modified = false;

  // 1. XP Resolution
  const xpMatch = text.match(/\[XP RESOLUTION:\s*Previous:\s*(\d+)\s*\|\s*Delta:\s*([+\-]?\d+)(?:\s*\((.*?)\))?\s*\|\s*New Total:\s*(\d+)\s*\/\s*(\d+)\]/i) ||
                  text.match(/\[XP RESOLUTION:.*?New Total:\s*(\d+)\s*\/\s*(\d+)\]/i);
  if (xpMatch) {
    const curXP = parseInt(xpMatch[xpMatch.length - 2]);
    const maxXP = parseInt(xpMatch[xpMatch.length - 1]);
    const xpStr = `${curXP} / ${maxXP}`;
    const xpEl = document.getElementById('val-xp');
    if (xpEl) xpEl.textContent = xpStr;

    if (campaignData.statusJson && campaignData.statusJson.progression) {
      campaignData.statusJson.progression.xp = curXP;
      campaignData.statusJson.progression.xp_threshold = maxXP;
      modified = true;
    }
    if (campaignData.status) {
      campaignData.status = campaignData.status.replace(/XP:\s*\d+\s*\/\s*\d+/i, `XP: ${xpStr}`);
      modified = true;
    }
  }

  // 2. Currency Resolution
  const currMatch = text.match(/\[CURRENCY RESOLUTION:.*?New Purse:\s*([^\]]+)\]/i);
  if (currMatch) {
    const newPurse = currMatch[1].trim();
    const purseEl = document.getElementById('val-purse');
    if (purseEl) purseEl.textContent = newPurse;

    if (campaignData.statusJson && campaignData.statusJson.purse) {
      campaignData.statusJson.purse.display = newPurse;
      const gMatch = newPurse.match(/(\d+)\s*G/i);
      const sMatch = newPurse.match(/(\d+)\s*S/i);
      const cMatch = newPurse.match(/(\d+)\s*C/i);
      if (gMatch) campaignData.statusJson.purse.gold = parseInt(gMatch[1]);
      if (sMatch) campaignData.statusJson.purse.silver = parseInt(sMatch[1]);
      if (cMatch) campaignData.statusJson.purse.copper = parseInt(cMatch[1]);
      modified = true;
    }
    if (campaignData.items) {
      campaignData.items = campaignData.items.replace(/(\*\*Current Coin\*\*:\s*`)[^`]+(`)/i, `$1${newPurse}$2`);
      modified = true;
    }
  }

  // 3. System Block (Turn + every metric declared in campaign_config.json)
  const sysMatch = text.match(/\[SYS:\s*(.*?)\]/i);
  if (sysMatch) {
    const parts = sysMatch[1].split('|').map(p => p.trim());
    const metrics = (activeConfig && activeConfig.metrics) || [];
    let turnParsed = false;

    parts.forEach(p => {
      const lower = p.toLowerCase();

      if (lower.startsWith('turn') || lower.startsWith('cycle')) {
        if (turnParsed) return;
        const num = p.match(/\d+/);
        if (num) {
          currentTurn = parseInt(num[0]);
          if (campaignData.statusJson) campaignData.statusJson.turn = currentTurn;
          modified = true;
          turnParsed = true;
        }
        return;
      }

      // Resolve this segment against the active campaign's declared metrics.
      const metric = metrics.find(m => {
        const label = String(m.label || '').toLowerCase();
        const id = String(m.id || '').toLowerCase();
        return (label && lower.startsWith(label)) || (id && lower.startsWith(id));
      });
      if (!metric || !campaignData.statusJson) return;

      if (metric.type === 'text') {
        const colon = p.indexOf(':');
        const raw = (colon >= 0 ? p.slice(colon + 1) : p.replace(/^[^\d]*/, '')).trim();
        if (raw && metric.path) {
          setNestedValue(campaignData.statusJson, metric.path, raw);
          modified = true;
        }
        return;
      }

      const nums = p.match(/-?\d+(?:\.\d+)?/g);
      if (!nums || nums.length === 0) return;

      if (metric.path) setNestedValue(campaignData.statusJson, metric.path, parseFloat(nums[0]));
      if (metric.max_path && nums.length > 1) {
        setNestedValue(campaignData.statusJson, metric.max_path, parseFloat(nums[1]));
      }
      modified = true;
    });
  }

  // Re-render HUD with updated values (sidebar + schema-driven metric pills)
  if (campaignData.statusJson && activeConfig) {
    renderSchemaDrivenStatus(campaignData.statusJson, activeConfig, campaignData.status);
    extractMetrics(campaignData.status, campaignData.items, campaignData.statusJson);
  }

  // Write updated state back to disk if folder is connected
  if (modified && dirHandle) {
    try {
      let campaignHandle = dirHandle;
      const selectedCampaign = campaignSelect ? campaignSelect.value : '';
      try {
        const campaignsDir = await dirHandle.getDirectoryHandle('CAMPAIGNS');
        campaignHandle = await campaignsDir.getDirectoryHandle(selectedCampaign);
      } catch(e) {}

      const gameplayDir = await campaignHandle.getDirectoryHandle('GAMEPLAY');
      if (campaignData.statusJson) {
        await writeTextFile(gameplayDir, 'status.json', JSON.stringify(campaignData.statusJson, null, 2));
      }
      if (campaignData.status) {
        await writeTextFile(gameplayDir, 'status.md', campaignData.status);
      }
      if (campaignData.items) {
        await writeTextFile(gameplayDir, 'items.md', campaignData.items);
      }
      console.log('Successfully mutated and persisted GAMEPLAY/status.json, status.md, and items.md to disk!');
    } catch (e) {
      console.error('Failed to persist mutated state to disk:', e);
    }
  }
}

function parseAndRenderNewChoices(text) {
  if (!text) return;
  let optionBlock = text;
  const optionsMatch = text.match(/\[OPTIONS(?: & TYPABLE REFERENCE)?\]([\s\S]*)/i);
  if (optionsMatch) {
    optionBlock = optionsMatch[1];
  }

  const lines = optionBlock.split('\n');
  const choices = [];
  const numberedChoiceRegex = /^(\d+)[\.\)]\s+(.*)/;
  const bulletChoiceRegex = /^[-*•]\s+(.*)/;

  for (let line of lines) {
    line = line.trim();
    if (!line) continue;
    if (line.includes('[XP RESOLUTION') || line.includes('[CURRENCY RESOLUTION') || line.includes('[SYS:') || line.includes('[ITEM RESOLUTION')) break;
    if (line.startsWith('---') || line.startsWith('===') || line.startsWith('#')) continue;

    const numMatch = line.match(numberedChoiceRegex);
    if (numMatch) {
      const cleanDesc = numMatch[2].replace(/\*\*/g, '').replace(/\*/g, '').replace(/`/g, '').trim();
      choices.push({ num: parseInt(numMatch[1]), text: cleanDesc });
    } else {
      const bulletMatch = line.match(bulletChoiceRegex);
      const rawDesc = bulletMatch ? bulletMatch[1].trim() : line;
      const cleanDesc = rawDesc.replace(/\*\*/g, '').replace(/\*/g, '').replace(/`/g, '').trim();
      if (cleanDesc.length > 5 && !cleanDesc.startsWith('[')) {
        choices.push({ num: choices.length + 1, text: cleanDesc });
      }
    }
  }

  if (choices.length > 0) {
    choiceGrid.innerHTML = '';
    selectedChoice = null;
    choices.forEach(c => {
      const btn = document.createElement('button');
      btn.className = 'choice-btn';
      btn.dataset.choice = c.num;
      btn.innerHTML = `<span class="choice-num">${c.num}.</span> <span class="choice-desc">${escapeHtml(c.text)}</span>`;
      choiceGrid.appendChild(btn);
    });
    setupChoiceButtonListeners();
  }
}

// File System Access & Multi-Campaign Workspace Loading
folderPickerBtn.addEventListener('click', async () => {
  if (!window.showDirectoryPicker) {
    alert("File System Access API is not supported in this browser (common on mobile browsers). You can continue playing seamlessly with built-in manifest data and local engine sync!");
    return;
  }
  try {
    dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
    syncStatus.textContent = dirHandle.name;
    syncStatus.className = 'status-pill status-connected';
    syncStatus.title = 'Workspace connected: ' + dirHandle.name;
    await saveStoredHandle(dirHandle);
    await loadWorkspace(dirHandle);
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.warn('Folder selection error:', err);
    }
  }
});

async function loadWorkspace(rootHandle) {
  try {
    let campaignHandle = rootHandle;
    const selectedCampaign = campaignSelect ? campaignSelect.value : '';
    
    // Reset active turns and view index immediately when loading a workspace/campaign
    campaignData.activeTurns = [];
    currentTurnViewIndex = -1;

    try {
      const campaignsDir = await rootHandle.getDirectoryHandle('CAMPAIGNS');
      
      // Auto-discover all campaign folders containing a campaign_config.json
      for await (const entry of campaignsDir.values()) {
        if (entry.kind === 'directory' && !entry.name.startsWith('_') && !entry.name.startsWith('.')) {
          try {
            const confText = await readTextFile(entry, 'campaign_config.json');
            const conf = JSON.parse(confText);
            campaignConfigs[entry.name] = conf;

            let exists = false;
            for (let i = 0; i < campaignSelect.options.length; i++) {
              if (campaignSelect.options[i].value === entry.name) {
                exists = true;
                break;
              }
            }
            if (!exists) {
              const opt = document.createElement('option');
              opt.value = entry.name;
              opt.textContent = (conf.title || entry.name).toUpperCase();
              campaignSelect.appendChild(opt);
            }
          } catch(e) {}
        }
      }

      campaignHandle = await campaignsDir.getDirectoryHandle(selectedCampaign);
    } catch (e) {
      // Direct campaign folder selected or root is already CAMPAIGNS
      try {
        campaignHandle = await rootHandle.getDirectoryHandle(selectedCampaign);
      } catch(e2) {
        // Fallback to rootHandle
      }
    }

    // 1. Load GAMEPLAY (JSON + MD)
    try {
      const gameplayDir = await campaignHandle.getDirectoryHandle('GAMEPLAY');
      
      // Load structured JSON files if available
      try {
        const statusJsonText = await readTextFile(gameplayDir, 'status.json');
        campaignData.statusJson = JSON.parse(statusJsonText);
      } catch(e) {}

      try {
        const relJsonText = await readTextFile(gameplayDir, 'relations.json');
        campaignData.relationsJson = JSON.parse(relJsonText);
      } catch(e) {}

      try {
        const itemsJsonText = await readTextFile(gameplayDir, 'items.json');
        campaignData.itemsJson = JSON.parse(itemsJsonText);
      } catch(e) {}

      // Load Markdown files
      try { campaignData.status = await readTextFile(gameplayDir, 'status.md'); } catch(e) {}
      try { campaignData.relations = await readTextFile(gameplayDir, 'relations.md'); } catch(e) {}
      try { campaignData.items = await readTextFile(gameplayDir, 'items.md'); } catch(e) {}
      try { campaignData.upcomingHooks = await readTextFile(gameplayDir, 'upcoming_hooks.md'); } catch(e) {
        campaignData.upcomingHooks = gameplayManifest[selectedCampaign]?.upcoming_hooks || '';
      }

      // Load Ontology if available
      try {
        const ontologyText = await readTextFile(campaignHandle, 'ontology.json');
        campaignData.ontologyJson = JSON.parse(ontologyText);
      } catch(e) {
        campaignData.ontologyJson = null;
      }

      // Load narrative steering from IDEAS if available
      try {
        const ideasDir = await campaignHandle.getDirectoryHandle('IDEAS');
        campaignData.narrativeSteering = await readTextFile(ideasDir, 'narrative_steering.md');
      } catch(e) {
        campaignData.narrativeSteering = gameplayManifest[selectedCampaign]?.narrative_steering || '';
      }
      
      activeConfig = campaignConfigs[selectedCampaign] || activeConfig;
      applyActiveCampaignConfig();
    } catch (e) {
      console.warn('Could not read GAMEPLAY folder for campaign:', selectedCampaign, e);
    }

    // 2. Load Active Turns
    try {
      const turnsDir = await campaignHandle.getDirectoryHandle('TURNS');
      const activeDir = await turnsDir.getDirectoryHandle('ACTIVE');
      campaignData.activeTurns = [];

      for await (const entry of activeDir.values()) {
        if (entry.kind === 'file' && entry.name.endsWith('.md')) {
          const content = await readTextFile(activeDir, entry.name);
          campaignData.activeTurns.push({ name: entry.name, content });
        }
      }
    } catch (e) {
      console.warn('No active turns found on disk in:', selectedCampaign);
    }

    if (campaignData.activeTurns.length > 0) {
      renderStoryStream(campaignData.activeTurns);
      const turnNums = campaignData.activeTurns.map(t => parseInt((t.name.match(/\d+/) || [0])[0]));
      const maxTurn = Math.max(...turnNums);
      if (maxTurn > 0) {
        currentTurn = maxTurn + 1;
        const turnEl = document.getElementById('val-turn');
        if (turnEl) turnEl.textContent = currentTurn;
      }
    } else if (gameplayManifest[selectedCampaign]?.active_turns?.length > 0) {
      campaignData.activeTurns = JSON.parse(JSON.stringify(gameplayManifest[selectedCampaign].active_turns));
      renderStoryStream(campaignData.activeTurns);
    } else {
      renderInitialCampaignScene(selectedCampaign);
    }

  } catch (err) {
    console.error('Failed to load workspace:', err);
  }
}

let currentTurnViewIndex = -1;

function renderStoryStream(turns) {
  if (!turns || turns.length === 0) return;
  turns.sort((a, b) => {
    const na = parseInt((a.name.match(/\d+/) || [0])[0]);
    const nb = parseInt((b.name.match(/\d+/) || [0])[0]);
    return na - nb;
  });

  // Default to the latest active turn
  if (currentTurnViewIndex < 0 || currentTurnViewIndex >= turns.length) {
    currentTurnViewIndex = turns.length - 1;
  }

  renderCurrentTurnView(turns);
}

function renderCurrentTurnView(turns) {
  storyStream.innerHTML = '';
  if (!turns || turns.length === 0) return;

  const totalTurns = turns.length;
  const turnData = turns[currentTurnViewIndex];
  if (!turnData) return;

  const turnNumMatch = turnData.name.match(/\d+/);
  const turnNumStr = turnNumMatch ? parseInt(turnNumMatch[0]) : turnData.name;
  const isLatest = currentTurnViewIndex === totalTurns - 1;

  // 1. Navigation Bar (Previous / Next / Latest)
  const navBar = document.createElement('div');
  navBar.className = 'turn-navigation-bar';
  navBar.innerHTML = `
    <button id="btn-prev-turn" class="action-btn small" ${currentTurnViewIndex <= 0 ? 'disabled' : ''}>
      ◀ Previous Turn
    </button>
    <span class="turn-nav-title">
      <strong>Turn ${turnNumStr}</strong>
      <span class="turn-nav-counter">(${currentTurnViewIndex + 1} of ${totalTurns}${isLatest ? ' • Latest' : ''})</span>
    </span>
    <div class="turn-nav-actions">
      <button id="btn-next-turn" class="action-btn small" ${isLatest ? 'disabled' : ''}>
        Next Turn ▶
      </button>
      ${!isLatest ? '<button id="btn-latest-turn" class="action-btn primary small" style="margin-left:6px;">Latest ⏩</button>' : ''}
    </div>
  `;
  storyStream.appendChild(navBar);

  // Wire up nav buttons
  const prevBtn = navBar.querySelector('#btn-prev-turn');
  const nextBtn = navBar.querySelector('#btn-next-turn');
  const latestBtn = navBar.querySelector('#btn-latest-turn');

  if (prevBtn && !prevBtn.disabled) {
    prevBtn.addEventListener('click', () => {
      if (currentTurnViewIndex > 0) {
        currentTurnViewIndex--;
        renderCurrentTurnView(turns);
      }
    });
  }
  if (nextBtn && !nextBtn.disabled) {
    nextBtn.addEventListener('click', () => {
      if (currentTurnViewIndex < totalTurns - 1) {
        currentTurnViewIndex++;
        renderCurrentTurnView(turns);
      }
    });
  }
  if (latestBtn) {
    latestBtn.addEventListener('click', () => {
      currentTurnViewIndex = totalTurns - 1;
      renderCurrentTurnView(turns);
    });
  }

  const rawContent = turnData.content || '';

  // Extract Active RECAL and render choices if viewing latest turn
  if (isLatest) {
    updateActiveRecalBanner(rawContent);
    parseAndRenderNewChoices(rawContent);
  }

  // Clean narrative separation
  const { cleanNarrative, receipts, optionsText } = splitTurnNarrativeAndReceipts(rawContent);

  // 2. Render Single Active Scene Card
  const card = document.createElement('div');
  card.className = 'scene-card';

  let receiptsHtml = '';
  if (receipts.length > 0 || (!isLatest && optionsText)) {
    let innerReceipts = '';
    if (receipts.length > 0) {
      innerReceipts += renderMarkdown(receipts.join('\n\n'));
    }
    if (!isLatest && optionsText) {
      innerReceipts += `<div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.08);"><strong>Offered Turn Options:</strong>\n${renderMarkdown(optionsText)}</div>`;
    }
    receiptsHtml = `
      <details class="turn-receipts-drawer">
        <summary class="receipts-summary">🧾 View Turn Receipts & Receipts Log</summary>
        <div class="receipts-body">${innerReceipts}</div>
      </details>
    `;
  }

  card.innerHTML = `
    <div class="turn-header">${escapeHtml(turnData.name.replace('.md', '').replace(/_/g, ' ').toUpperCase())}</div>
    <div class="turn-content">${renderMarkdown(cleanNarrative)}</div>
    ${receiptsHtml}
  `;
  storyStream.appendChild(card);

  // If viewing an archived past turn, show a notice banner
  if (!isLatest) {
    const banner = document.createElement('div');
    banner.className = 'past-turn-banner';
    banner.innerHTML = `
      <span>📖 You are viewing an earlier turn record.</span>
      <button id="banner-return-latest" class="action-btn primary small">Return to Active Turn ⏩</button>
    `;
    storyStream.appendChild(banner);
    banner.querySelector('#banner-return-latest').addEventListener('click', () => {
      currentTurnViewIndex = totalTurns - 1;
      renderCurrentTurnView(turns);
    });
  }

  storyStream.scrollTop = 0;
}

function splitTurnNarrativeAndReceipts(rawContent) {
  if (!rawContent) return { cleanNarrative: '', receipts: [], optionsText: '' };

  const receipts = [];
  let narrative = rawContent;
  let optionsText = '';

  // Extract receipt blocks: [XP RESOLUTION...], [CURRENCY RESOLUTION...], [ITEM RESOLUTION...], [SYS: ...]
  const receiptRegex = /\[(XP RESOLUTION|CURRENCY RESOLUTION|ITEM RESOLUTION|SYS)[^\]]*\]/gi;
  let match;
  while ((match = receiptRegex.exec(rawContent)) !== null) {
    receipts.push(match[0]);
  }

  // Extract options text if present
  const optionsMatch = narrative.match(/\[OPTIONS(?: & TYPABLE REFERENCE)?\]([\s\S]*?)(?=\[SYS:|\n\n\[|$)/i);
  if (optionsMatch) {
    optionsText = optionsMatch[1].trim();
  }

  // Remove [OPTIONS & TYPABLE REFERENCE] section and everything following it
  narrative = narrative.replace(/\[OPTIONS(?: & TYPABLE REFERENCE)?\][\s\S]*?(?=\[SYS:|\n\n\[|$)/i, '');
  narrative = narrative.replace(/\[OPTIONS(?: & TYPABLE REFERENCE)?\][\s\S]*/i, '');

  // Remove standalone receipt tags from narrative
  narrative = narrative.replace(/\[(XP RESOLUTION|CURRENCY RESOLUTION|ITEM RESOLUTION|SYS)[^\]]*\]/gi, '');

  // Strip trailing horizontal rules and extra whitespace
  narrative = narrative.replace(/(?:---|\*\*\*)\s*$/gm, '').trim();

  return { cleanNarrative: narrative, receipts, optionsText };
}

function updateActiveRecalBanner(text) {
  const recalBanner = document.getElementById('active-recal-banner');
  const recalTextEl = document.getElementById('active-recal-text');
  const recalExpiresEl = document.getElementById('active-recal-expires');
  if (!recalBanner) return;

  if (!text) {
    recalBanner.classList.add('hidden');
    return;
  }

  const match = text.match(/Active RECAL:\s*([^\]\n]+?)(?:\s*-\s*Expires:\s*Turn\s*(\d+)|\]|\n|$)/i);
  if (match && match[1].trim()) {
    const recalText = match[1].trim();
    const expiresTurn = match[2];
    recalBanner.classList.remove('hidden');
    if (recalTextEl) recalTextEl.textContent = recalText;
    if (recalExpiresEl) {
      recalExpiresEl.textContent = expiresTurn ? `(Expires: Turn ${expiresTurn})` : '';
    }
  } else {
    recalBanner.classList.add('hidden');
  }
}

// Wire up clear recal button
const btnClearRecal = document.getElementById('btn-clear-recal');
if (btnClearRecal) {
  btnClearRecal.addEventListener('click', () => {
    const recalBanner = document.getElementById('active-recal-banner');
    if (recalBanner) recalBanner.classList.add('hidden');
  });
}

async function readTextFile(dirHandle, filename) {
  const fileHandle = await dirHandle.getFileHandle(filename);
  const file = await fileHandle.getFile();
  return await file.text();
}

async function writeTextFile(dirHandle, filename, content) {
  const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(content);
  await writable.close();
}

function extractMetrics(statusText, itemsText = '', statusJson = null) {
  const combined = (statusText || '') + '\n' + (itemsText || '');

  if (!activeConfig || !activeConfig.metrics) return;

  activeConfig.metrics.forEach(m => {
    const el = document.getElementById(`val-${m.id}`);
    if (!el) return;

    // 1. Try structured statusJson first (highest priority & zero ambiguity)
    if (statusJson && m.path) {
      let val = getNestedValue(statusJson, m.path);
      if ((val === undefined || val === null) && m.id === 'purse' && statusJson.purse) {
        val = statusJson.purse;
      }
      if (val !== undefined && val !== null) {
        if (m.id === 'turn') {
          currentTurn = parseInt(val) || currentTurn;
          el.textContent = currentTurn;
          return;
        }
        if (m.id === 'purse' || typeof val === 'object') {
          if (typeof val === 'object') {
            if (val.display) {
              el.textContent = val.display;
              return;
            }
            const parts = [];
            if (val.gold) parts.push(`${val.gold}G`);
            if (val.silver) parts.push(`${val.silver}S`);
            if (val.copper) parts.push(`${val.copper}C`);
            if (parts.length > 0) {
              el.textContent = parts.join(' ');
              return;
            }
          }
        }
        if (m.max_path) {
          const maxVal = getNestedValue(statusJson, m.max_path);
          el.textContent = maxVal !== undefined ? `${val} / ${maxVal}` : val;
          return;
        }
        el.textContent = val;
        return;
      }
    }

    // 2. Fallback to Regex / text parsing
    if (m.id === 'turn') {
      const turnMatch = combined.match(/(?:Turn|Cycle)\s*[:\*\s]*(\d+)/i);
      if (turnMatch) currentTurn = parseInt(turnMatch[1]);
      el.textContent = currentTurn;
    } else if (m.id === 'xp') {
      const xpMatch = combined.match(/XP\s*[:\*\s]*(\d+)\s*\/\s*(\d+)/i);
      if (xpMatch) {
        el.textContent = `${xpMatch[1]} / ${xpMatch[2]}`;
      }
    } else if (m.id === 'strain') {
      const strainMatch = combined.match(/Strain(?:\s*Buffer)?\s*[:\*\s]*([0-9]+)(?:\s*\/\s*([0-9]+))?/i);
      if (strainMatch) {
        el.textContent = strainMatch[2] ? `${strainMatch[1]} / ${strainMatch[2]}` : strainMatch[1];
      }
    } else if (m.id === 'purse') {
      const coinMatch = combined.match(/Current Coin\**:\s*`([^`]+)`/i) ||
                        combined.match(/Currency Purse\**:\s*([^\n\r]+)/i) ||
                        combined.match(/Purse\**:\s*([^\n\r]+)/i);
      if (coinMatch) {
        let purseStr = coinMatch[1]
          .replace(/\*\*/g, '')
          .replace(/0\s*Platinum\s*[,\|]?\s*/i, '')
          .replace(/(\d+)\s*Gold(?:\s*Crowns?)?/gi, '$1G')
          .replace(/(\d+)\s*Silver(?:\s*Marks?)?/gi, '$1S')
          .replace(/(\d+)\s*Copper(?:\s*Cogs?)?/gi, '$1C')
          .replace(/\s*,\s*/g, ' ')
          .replace(/\s*\|\s*/g, ' ')
          .replace(/\s+/g, ' ')
          .trim();
        purseStr = purseStr.replace(/\.$/, '');
        el.textContent = purseStr;
      }
    } else if (m.regex) {
      const reg = new RegExp(m.regex, 'i');
      const match = combined.match(reg);
      if (match) {
        el.textContent = match[2] ? `${match[1]} / ${match[2]}` : match[1];
      }
    }
  });
}

async function saveTurnToDisk(turnNum, playerAction, gmResponse) {
  try {
    let campaignHandle = dirHandle;
    const selectedCampaign = campaignSelect ? campaignSelect.value : '';
    try {
      const campaignsDir = await dirHandle.getDirectoryHandle('CAMPAIGNS');
      campaignHandle = await campaignsDir.getDirectoryHandle(selectedCampaign);
    } catch(e) {}

    const turnsDir = await campaignHandle.getDirectoryHandle('TURNS');
    const activeDir = await turnsDir.getDirectoryHandle('ACTIVE');

    const turnFile = `turn_${String(turnNum).padStart(4, '0')}.md`;
    const turnContent = `# Turn ${turnNum}\n\n## Player Action\n${playerAction}\n\n## GM Response\n${gmResponse}\n`;
    const fileHandle = await activeDir.getFileHandle(turnFile, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(turnContent);
    await writable.close();
    console.log(`Successfully written: ${turnFile}`);
  } catch (err) {
    console.error('Failed to save turn file:', err);
  }
}

function appendCard(header, htmlContent, isPlayer = false) {
  const card = document.createElement('div');
  card.className = isPlayer ? 'scene-card player-card' : 'scene-card';
  
  const headerEl = document.createElement('div');
  headerEl.className = 'turn-header';
  headerEl.textContent = header;
  
  const bodyEl = document.createElement('div');
  bodyEl.className = 'turn-content';
  bodyEl.innerHTML = htmlContent;

  card.appendChild(headerEl);
  card.appendChild(bodyEl);
  storyStream.appendChild(card);
  storyStream.scrollTop = storyStream.scrollHeight;
  return bodyEl;
}
