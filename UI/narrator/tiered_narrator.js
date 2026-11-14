/**
 * UI/narrator/tiered_narrator.js
 * ==============================
 * Master Tiered Narration Coordinator and Capability Detection Engine.
 *
 * Implements Issue #17 R6, R7, R8, R9:
 * - R6: Three narration tiers:
 *   1. Authored/offline (pre-written/template prose from passage text, keyless, zero network).
 *   2. Local model (in-browser WebGPU/WASM or local endpoint).
 *   3. Cloud LLM (BYO API key via Gemini or OpenRouter).
 * - R7: Same Outcome contract across tiers:
 *   DeterministicCore.Core.resolve is executed FIRST to compute the exact Outcome.
 *   The narration tier only generates the aesthetic prose; state mutations remain identical.
 * - R8: Narration never gates progress:
 *   If a model times out, network fails, or credentials are missing, it falls back
 *   immediately and seamlessly to Tier 1 Authored prose without throwing or blocking gameplay.
 */

(function (global) {
  'use strict';

  // Import dependencies if in CommonJS
  let Core = null;
  let authoredNarrator = null;
  let localNarrator = null;
  let cloudNarrator = null;

  if (typeof module !== 'undefined' && module.exports) {
    try {
      const coreMod = require('../core/deterministic_core.js');
      Core = coreMod.Core;
    } catch (e) {}

    try {
      authoredNarrator = require('./authored_narrator.js').authoredNarrator;
      localNarrator = require('./local_narrator.js').localNarrator;
      cloudNarrator = require('./cloud_narrator.js').cloudNarrator;
    } catch (e) {}
  }

  const TIERS = {
    AUTHORED: 1,
    LOCAL: 2,
    CLOUD: 3
  };

  const TIER_NAMES = {
    1: 'Tier 1: Authored / Offline',
    2: 'Tier 2: Local Model (WebGPU/Local)',
    3: 'Tier 3: Cloud LLM (BYO Key)'
  };

  class TieredNarrator {
    constructor() {
      this.TIERS = TIERS;
      this.TIER_NAMES = TIER_NAMES;
    }

    _getAuthoredNarrator() {
      if (authoredNarrator) return authoredNarrator;
      if (typeof window !== 'undefined' && window.authoredNarrator) return window.authoredNarrator;
      throw new Error('AuthoredNarrator adapter not available');
    }

    _getLocalNarrator() {
      if (localNarrator) return localNarrator;
      if (typeof window !== 'undefined' && window.localNarrator) return window.localNarrator;
      throw new Error('LocalNarrator adapter not available');
    }

    _getCloudNarrator() {
      if (cloudNarrator) return cloudNarrator;
      if (typeof window !== 'undefined' && window.cloudNarrator) return window.cloudNarrator;
      throw new Error('CloudNarrator adapter not available');
    }

    _getCore(providedCore = null) {
      if (providedCore) return providedCore;
      if (Core) return Core;
      if (typeof window !== 'undefined' && window.DeterministicCore && window.DeterministicCore.Core) {
        return window.DeterministicCore.Core;
      }
      throw new Error('DeterministicCore not available');
    }

    /**
     * Detect system capabilities and determine recommended narration tier.
     */
    async detectCapabilities({ apiKey = null, localEndpoint = null } = {}) {
      const isOnline = typeof navigator !== 'undefined' ? Boolean(navigator.onLine) : true;
      const hasGpu = typeof navigator !== 'undefined' && Boolean(navigator.gpu);

      const cloudAdapter = this._getCloudNarrator();
      const hasApiKey = cloudAdapter.isConfigured(apiKey);

      let localActive = false;
      try {
        const localAdapter = this._getLocalNarrator();
        const localStatus = await localAdapter.detectCapability(localEndpoint);
        localActive = localStatus.localEndpointActive || localStatus.hasWebGpu;
      } catch (e) {
        localActive = false;
      }

      let recommendedTier = TIERS.AUTHORED;
      if (hasApiKey && isOnline) {
        recommendedTier = TIERS.CLOUD;
      } else if (localActive) {
        recommendedTier = TIERS.LOCAL;
      }

      return {
        isOnline,
        hasGpu,
        hasApiKey,
        localActive,
        recommendedTier,
        recommendedTierName: TIER_NAMES[recommendedTier],
        availableTiers: [
          TIERS.AUTHORED,
          ...(localActive ? [TIERS.LOCAL] : []),
          ...(hasApiKey && isOnline ? [TIERS.CLOUD] : [])
        ]
      };
    }

    /**
     * Resolve a turn deterministically, then generate narration prose through the
     * preferred tier with automatic non-blocking fallback (R7, R8).
     *
     * @param {Object} params
     * @param {Object} params.state - Current game state
     * @param {string|number|Object} params.action - Player action taken
     * @param {Object} [params.config] - Optional campaign rules & seed configuration
     * @param {number} [params.preferredTier] - Desired narration tier (1, 2, or 3)
     * @param {Object} [params.context] - Narrative context (scene anchor, character, etc.)
     * @param {Object} [params.coreInstance] - Optional Core override
     * @returns {Promise<{ outcome: Object, narration: Object }>}
     */
    async resolveTurn({
      state,
      action,
      config = {},
      preferredTier = null,
      context = {},
      coreInstance = null,
      apiKey = null,
      model = null,
      pacing = 'standard',
      localEndpoint = null
    }) {
      // 1. STEP 1 (R1, R7): Run Deterministic Turn Resolution FIRST
      const core = this._getCore(coreInstance);
      const outcome = core.resolve(state, action, config);

      // Determine requested tier
      let targetTier = preferredTier;
      if (!targetTier) {
        if (typeof localStorage !== 'undefined') {
          const storedTier = localStorage.getItem('cyoa_narration_tier');
          targetTier = storedTier ? parseInt(storedTier, 10) : TIERS.AUTHORED;
        } else {
          targetTier = TIERS.AUTHORED;
        }
      }

      let prose = '';
      let tierUsed = TIERS.AUTHORED;
      let fallbackOccurred = false;
      let narrationError = null;

      // 2. STEP 2 (R6, R8): Execute Tier with graceful non-blocking degradation
      if (targetTier === TIERS.CLOUD) {
        try {
          const cloudAdapter = this._getCloudNarrator();
          prose = await cloudAdapter.generateNarrative({
            action,
            outcome,
            context,
            apiKey,
            model,
            pacing
          });
          tierUsed = TIERS.CLOUD;
        } catch (err) {
          console.warn('Tier 3 (Cloud) narration failed, attempting fallback to Tier 1:', err.message);
          fallbackOccurred = true;
          narrationError = err.message;
        }
      } else if (targetTier === TIERS.LOCAL) {
        try {
          const localAdapter = this._getLocalNarrator();
          prose = await localAdapter.generateNarrative({
            action,
            outcome,
            context,
            endpoint: localEndpoint
          });
          tierUsed = TIERS.LOCAL;
        } catch (err) {
          console.warn('Tier 2 (Local) narration failed, attempting fallback to Tier 1:', err.message);
          fallbackOccurred = true;
          narrationError = err.message;
        }
      }

      // 3. STEP 3 (R1, R8): Fallback to Tier 1 Authored/Offline if needed or requested
      if (!prose) {
        try {
          const authoredAdapter = this._getAuthoredNarrator();
          prose = authoredAdapter.generateNarrative({
            action,
            outcome,
            context
          });
          tierUsed = TIERS.AUTHORED;
        } catch (authErr) {
          // Extreme fallback - should never happen
          prose = `You execute: "${action}". The outcome is recorded.\n\n[OPTIONS]\n` +
            (outcome.offered_choices || []).map(c => `${c.index}. ${c.text}`).join('\n');
          tierUsed = TIERS.AUTHORED;
          narrationError = authErr.message;
        }
      }

      return {
        outcome,
        narration: {
          text: prose,
          tierRequested: targetTier,
          tierUsed: tierUsed,
          tierName: TIER_NAMES[tierUsed] || `Tier ${tierUsed}`,
          fallbackOccurred,
          error: narrationError
        }
      };
    }
  }

  const tieredInstance = new TieredNarrator();

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      TieredNarrator,
      TIERS,
      TIER_NAMES,
      tieredNarrator: tieredInstance
    };
  }

  if (typeof window !== 'undefined') {
    window.TieredNarrator = TieredNarrator;
    window.TIERS = TIERS;
    window.TIER_NAMES = TIER_NAMES;
    window.tieredNarrator = tieredInstance;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
