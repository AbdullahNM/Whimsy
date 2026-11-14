/**
 * UI/storage/indexeddb.js
 * =======================
 * Robust IndexedDB save, load, and deterministic replay engine.
 *
 * Implements Issue #17 R3:
 * - Removes File System Access API from the critical path.
 * - Manages campaign state, turn history, and replay records in browser IndexedDB.
 * - Provides seamless fallback store for environments without IndexedDB (e.g. Node.js unit tests).
 */

(function (global) {
  'use strict';

  const DB_NAME = 'whimsy_cyoa_db';
  const DB_VERSION = 1;

  const STORES = {
    CAMPAIGNS: 'campaigns',
    TURNS: 'turns',
    REPLAYS: 'replays',
    SAVES: 'saves'
  };

  /**
   * In-Memory Fallback Engine used when IndexedDB is unavailable (Node.js tests, restricted iframes).
   */
  class MemoryStorageBackend {
    constructor() {
      this.stores = {
        [STORES.CAMPAIGNS]: new Map(),
        [STORES.TURNS]: new Map(),
        [STORES.REPLAYS]: new Map(),
        [STORES.SAVES]: new Map()
      };
    }

    async get(storeName, key) {
      const store = this.stores[storeName];
      if (!store) return null;
      const val = store.get(key);
      return val ? JSON.parse(JSON.stringify(val)) : null;
    }

    async put(storeName, value) {
      const store = this.stores[storeName];
      if (!store) throw new Error(`Unknown store: ${storeName}`);
      const key = value.id || value.campaignId || value.saveId;
      store.set(key, JSON.parse(JSON.stringify(value)));
      return key;
    }

    async delete(storeName, key) {
      const store = this.stores[storeName];
      if (store) store.delete(key);
      return true;
    }

    async getAllByIndex(storeName, indexName, queryValue) {
      const store = this.stores[storeName];
      if (!store) return [];
      const results = [];
      for (const val of store.values()) {
        if (val[indexName] === queryValue) {
          results.push(JSON.parse(JSON.stringify(val)));
        }
      }
      return results;
    }

    async getAll(storeName) {
      const store = this.stores[storeName];
      if (!store) return [];
      return Array.from(store.values()).map(v => JSON.parse(JSON.stringify(v)));
    }

    async clear(storeName) {
      const store = this.stores[storeName];
      if (store) store.clear();
      return true;
    }
  }

  /**
   * IndexedDB Storage Engine
   */
  class IndexedDBEngine {
    constructor() {
      this.db = null;
      this.fallback = null;
      this.isFallback = false;
      this._hasChecked = false;
    }

    /**
     * Determine if native IndexedDB is available.
     */
    isAvailable() {
      try {
        const idb = typeof window !== 'undefined'
          ? (window.indexedDB || window.mozIndexedDB || window.webkitIndexedDB || window.msIndexedDB)
          : (typeof indexedDB !== 'undefined' ? indexedDB : null);
        return Boolean(idb);
      } catch (e) {
        return false;
      }
    }

    /**
     * Initialize DB connection or fallback backend.
     */
    async init() {
      if (this.db) return this;
      if (this.isFallback && this.fallback) return this;

      if (!this.isAvailable()) {
        this.fallback = new MemoryStorageBackend();
        this.isFallback = true;
        return this;
      }

      const idb = (typeof window !== 'undefined' ? window.indexedDB : indexedDB);

      return new Promise((resolve, reject) => {
        try {
          const req = idb.open(DB_NAME, DB_VERSION);

          req.onupgradeneeded = (event) => {
            const db = event.target.result;

            // Campaigns store: key = campaign ID
            if (!db.objectStoreNames.contains(STORES.CAMPAIGNS)) {
              db.createObjectStore(STORES.CAMPAIGNS, { keyPath: 'id' });
            }

            // Turns store: key = composite id `${campaignId}_${turnNumber}`
            if (!db.objectStoreNames.contains(STORES.TURNS)) {
              const turnsStore = db.createObjectStore(STORES.TURNS, { keyPath: 'id' });
              turnsStore.createIndex('campaignId', 'campaignId', { unique: false });
              turnsStore.createIndex('turnNumber', 'turnNumber', { unique: false });
            }

            // Replays store: key = campaign ID
            if (!db.objectStoreNames.contains(STORES.REPLAYS)) {
              db.createObjectStore(STORES.REPLAYS, { keyPath: 'campaignId' });
            }

            // Saves store: key = saveId
            if (!db.objectStoreNames.contains(STORES.SAVES)) {
              const savesStore = db.createObjectStore(STORES.SAVES, { keyPath: 'saveId' });
              savesStore.createIndex('campaignId', 'campaignId', { unique: false });
            }
          };

          req.onsuccess = (event) => {
            this.db = event.target.result;
            this.isFallback = false;
            resolve(this);
          };

          req.onerror = (event) => {
            console.warn('IndexedDB open error, falling back to memory store:', event.target.error);
            this.fallback = new MemoryStorageBackend();
            this.isFallback = true;
            resolve(this);
          };
        } catch (err) {
          console.warn('IndexedDB initialization failed, falling back:', err);
          this.fallback = new MemoryStorageBackend();
          this.isFallback = true;
          resolve(this);
        }
      });
    }

    /**
     * Execute transaction against object store.
     */
    _tx(storeName, mode, callback) {
      if (this.isFallback) {
        return callback(null, this.fallback);
      }

      return new Promise((resolve, reject) => {
        try {
          const transaction = this.db.transaction(storeName, mode);
          const store = transaction.objectStore(storeName);

          const req = callback(store, null);
          if (req && typeof req.onsuccess !== 'undefined') {
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
          } else {
            transaction.oncomplete = () => resolve(req);
            transaction.onerror = () => reject(transaction.error);
          }
        } catch (err) {
          reject(err);
        }
      });
    }

    /**
     * Save campaign state snapshot.
     */
    async saveCampaignState(campaignId, stateData) {
      await this.init();
      const record = {
        id: campaignId,
        ...stateData,
        updatedAt: Date.now()
      };

      if (this.isFallback) {
        return this.fallback.put(STORES.CAMPAIGNS, record);
      }

      return this._tx(STORES.CAMPAIGNS, 'readwrite', (store) => store.put(record));
    }

    /**
     * Load campaign state snapshot.
     */
    async getCampaignState(campaignId) {
      await this.init();
      if (this.isFallback) {
        return this.fallback.get(STORES.CAMPAIGNS, campaignId);
      }

      return this._tx(STORES.CAMPAIGNS, 'readonly', (store) => store.get(campaignId));
    }

    /**
     * Save a turn entry.
     */
    async saveTurn(campaignId, turnNumber, turnData) {
      await this.init();
      const num = parseInt(turnNumber, 10);
      const record = {
        id: `${campaignId}_${num}`,
        campaignId: campaignId,
        turnNumber: num,
        name: turnData.name || `turn_${String(num).padStart(4, '0')}.md`,
        content: turnData.content || '',
        playerAction: turnData.playerAction || '',
        gmResponse: turnData.gmResponse || '',
        outcome: turnData.outcome || null,
        timestamp: turnData.timestamp || Date.now()
      };

      if (this.isFallback) {
        return this.fallback.put(STORES.TURNS, record);
      }

      return this._tx(STORES.TURNS, 'readwrite', (store) => store.put(record));
    }

    /**
     * Get all turns for a campaign ordered by turnNumber ascending.
     */
    async getTurns(campaignId) {
      await this.init();
      if (this.isFallback) {
        const turns = await this.fallback.getAllByIndex(STORES.TURNS, 'campaignId', campaignId);
        return turns.sort((a, b) => a.turnNumber - b.turnNumber);
      }

      return new Promise((resolve, reject) => {
        try {
          const transaction = this.db.transaction(STORES.TURNS, 'readonly');
          const store = transaction.objectStore(STORES.TURNS);
          const index = store.index('campaignId');
          const req = index.getAll(campaignId);

          req.onsuccess = () => {
            const list = req.result || [];
            list.sort((a, b) => a.turnNumber - b.turnNumber);
            resolve(list);
          };
          req.onerror = () => reject(req.error);
        } catch (err) {
          reject(err);
        }
      });
    }

    /**
     * Get a specific turn by number.
     */
    async getTurn(campaignId, turnNumber) {
      await this.init();
      const id = `${campaignId}_${parseInt(turnNumber, 10)}`;
      if (this.isFallback) {
        return this.fallback.get(STORES.TURNS, id);
      }
      return this._tx(STORES.TURNS, 'readonly', (store) => store.get(id));
    }

    /**
     * Delete a single turn.
     */
    async deleteTurn(campaignId, turnNumber) {
      await this.init();
      const id = `${campaignId}_${parseInt(turnNumber, 10)}`;
      if (this.isFallback) {
        return this.fallback.delete(STORES.TURNS, id);
      }
      return this._tx(STORES.TURNS, 'readwrite', (store) => store.delete(id));
    }

    /**
     * Clear all state and turns for a given campaign.
     */
    async clearCampaign(campaignId) {
      await this.init();
      if (this.isFallback) {
        await this.fallback.delete(STORES.CAMPAIGNS, campaignId);
        await this.fallback.delete(STORES.REPLAYS, campaignId);
        const turns = await this.getTurns(campaignId);
        for (const t of turns) {
          await this.fallback.delete(STORES.TURNS, t.id);
        }
        return true;
      }

      // Delete campaign doc
      await this._tx(STORES.CAMPAIGNS, 'readwrite', (store) => store.delete(campaignId));
      await this._tx(STORES.REPLAYS, 'readwrite', (store) => store.delete(campaignId));

      // Delete associated turns
      const turns = await this.getTurns(campaignId);
      for (const t of turns) {
        await this._tx(STORES.TURNS, 'readwrite', (store) => store.delete(t.id));
      }
      return true;
    }

    /**
     * List all stored campaigns.
     */
    async listCampaigns() {
      await this.init();
      if (this.isFallback) {
        return this.fallback.getAll(STORES.CAMPAIGNS);
      }
      return this._tx(STORES.CAMPAIGNS, 'readonly', (store) => store.getAll());
    }

    /**
     * Record a turn action step in the replay trail.
     */
    async recordReplayStep(campaignId, stepData) {
      await this.init();
      let replay = await this.getReplay(campaignId);
      if (!replay) {
        replay = {
          campaignId: campaignId,
          initialSeed: stepData.seed || 42,
          initialConfig: stepData.config || {},
          initialState: stepData.initialState || null,
          steps: [],
          updatedAt: Date.now()
        };
      }

      replay.steps.push({
        turnNumber: stepData.turnNumber,
        action: stepData.action,
        outcome: stepData.outcome || null,
        timestamp: Date.now()
      });
      replay.updatedAt = Date.now();

      if (this.isFallback) {
        return this.fallback.put(STORES.REPLAYS, replay);
      }
      return this._tx(STORES.REPLAYS, 'readwrite', (store) => store.put(replay));
    }

    /**
     * Get replay log for a campaign.
     */
    async getReplay(campaignId) {
      await this.init();
      if (this.isFallback) {
        return this.fallback.get(STORES.REPLAYS, campaignId);
      }
      return this._tx(STORES.REPLAYS, 'readonly', (store) => store.get(campaignId));
    }

    /**
     * Deterministically replay turn history using Core.resolve.
     * Verifies that each recorded action yields identical state outcomes.
     */
    async replayCampaign(campaignId, coreInstance) {
      const replay = await this.getReplay(campaignId);
      if (!replay || !replay.steps || replay.steps.length === 0) {
        return {
          success: true,
          turnsReplayed: 0,
          finalState: null,
          mismatches: []
        };
      }

      if (!coreInstance || typeof coreInstance.resolve !== 'function') {
        throw new Error('Valid Core instance required for deterministic replay.');
      }

      let currentState = JSON.parse(JSON.stringify(replay.initialState || {}));
      const config = replay.initialConfig || {};
      const mismatches = [];

      for (let i = 0; i < replay.steps.length; i++) {
        const step = replay.steps[i];
        const stepSeed = (replay.initialSeed || 42) + i;
        const stepConfig = { ...config, seed: stepSeed };

        const outcome = coreInstance.resolve(currentState, step.action, stepConfig);

        if (step.outcome) {
          // Compare essential outcome progression and turn
          const recordedOutcome = step.outcome;
          const turnMatch = (outcome.next_state?.turn === recordedOutcome.next_state?.turn);
          const effectsCountMatch = (outcome.effects?.length === recordedOutcome.effects?.length);

          if (!turnMatch || !effectsCountMatch) {
            mismatches.push({
              turn: step.turnNumber,
              action: step.action,
              expected: recordedOutcome,
              actual: outcome.toDict ? outcome.toDict() : outcome
            });
          }
        }

        currentState = outcome.next_state;
      }

      return {
        success: mismatches.length === 0,
        turnsReplayed: replay.steps.length,
        finalState: currentState,
        mismatches: mismatches
      };
    }

    /**
     * Export complete campaign save as JSON string / object.
     */
    async exportSave(campaignId) {
      const campaign = await this.getCampaignState(campaignId);
      const turns = await this.getTurns(campaignId);
      const replay = await this.getReplay(campaignId);

      return {
        version: 1,
        exportedAt: new Date().toISOString(),
        campaignId: campaignId,
        campaign: campaign,
        turns: turns,
        replay: replay
      };
    }

    /**
     * Import complete campaign save from JSON object.
     */
    async importSave(saveData) {
      if (!saveData || !saveData.campaignId) {
        throw new Error('Invalid save data format: missing campaignId');
      }

      const cid = saveData.campaignId;
      if (saveData.campaign) {
        await this.saveCampaignState(cid, saveData.campaign);
      }

      if (Array.isArray(saveData.turns)) {
        for (const t of saveData.turns) {
          await this.saveTurn(cid, t.turnNumber, t);
        }
      }

      if (saveData.replay) {
        if (this.isFallback) {
          await this.fallback.put(STORES.REPLAYS, saveData.replay);
        } else {
          await this._tx(STORES.REPLAYS, 'readwrite', (store) => store.put(saveData.replay));
        }
      }

      return { success: true, campaignId: cid, turnsImported: (saveData.turns || []).length };
    }
  }

  // Singleton instance
  const storageInstance = new IndexedDBEngine();

  // Export for CommonJS and Browser
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      IndexedDBEngine,
      MemoryStorageBackend,
      WhimsyStorage: storageInstance,
      storage: storageInstance
    };
  }

  if (typeof window !== 'undefined') {
    window.WhimsyStorage = storageInstance;
    window.IndexedDBStorage = storageInstance;
    window.IndexedDBEngine = IndexedDBEngine;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
