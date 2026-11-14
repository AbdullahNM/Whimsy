/**
 * UI/narrator/local_narrator.js
 * =============================
 * Tier 2 Local Model Narrator (WebGPU / WASM / Local Endpoint).
 *
 * Implements Issue #17 R6 (Tier 2), R7, R8:
 * - Employs in-browser WebGPU/WASM or local endpoint (e.g. Ollama, LM Studio, local engine).
 * - Constrained strictly by deterministic outcome.
 * - Enforces timeout protection and non-blocking fallback (R8).
 */

(function (global) {
  'use strict';

  class LocalNarrator {
    constructor() {
      this.tier = 2;
      this.name = 'Local Model (WebGPU / WASM / Local Endpoint)';
      this.defaultTimeoutMs = 8000;
    }

    /**
     * Detect local model capability.
     */
    async detectCapability(customEndpoint = null) {
      const hasWebGpu = typeof navigator !== 'undefined' && Boolean(navigator.gpu);
      let localEndpointActive = false;

      const endpoint = customEndpoint || 'http://localhost:8000/generate';
      if (typeof fetch !== 'undefined') {
        try {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 800);
          const res = await fetch(endpoint.replace('/generate', '/health') || endpoint, {
            method: 'GET',
            signal: controller.signal
          }).catch(() => null);
          clearTimeout(timer);
          if (res && (res.ok || res.status === 404 || res.status === 405)) {
            localEndpointActive = true;
          }
        } catch (e) {
          localEndpointActive = false;
        }
      }

      return {
        hasWebGpu,
        localEndpointActive,
        isAvailable: hasWebGpu || localEndpointActive
      };
    }

    /**
     * Generate narrative prose using local model endpoint.
     */
    async generateNarrative({ action, outcome, context = {}, endpoint = 'http://localhost:8000/generate', timeoutMs = null }) {
      if (!outcome) {
        throw new Error('LocalNarrator requires a valid deterministic Outcome');
      }

      const timeout = timeoutMs || this.defaultTimeoutMs;
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      let timer = null;

      try {
        if (controller) {
          timer = setTimeout(() => controller.abort(), timeout);
        }

        const prompt = this._buildConstrainedPrompt(action, outcome, context);

        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: prompt,
            action: typeof action === 'string' ? action : action.text,
            outcome: outcome.toDict ? outcome.toDict() : outcome,
            context: context,
            max_tokens: 350,
            temperature: 0.7
          }),
          signal: controller ? controller.signal : undefined
        });

        if (timer) clearTimeout(timer);

        if (!res.ok) {
          throw new Error(`Local model endpoint returned HTTP ${res.status}`);
        }

        const data = await res.json();
        const text = data.text || data.response || data.generated_text || data.choices?.[0]?.text;
        if (!text || typeof text !== 'string' || !text.trim()) {
          throw new Error('Local model returned empty narrative response');
        }

        return text.trim();
      } catch (err) {
        if (timer) clearTimeout(timer);
        if (err.name === 'AbortError') {
          throw new Error(`Local model timed out after ${timeout}ms`);
        }
        throw err;
      }
    }

    _buildConstrainedPrompt(action, outcome, context) {
      const nextState = outcome.next_state || {};
      const actionText = typeof action === 'string' ? action : (action.text || '');
      const charName = nextState.character?.name || context.character?.name || 'The protagonist';
      const loc = nextState.scene_anchor?.location || 'Unknown Area';

      return `You are the Game Master for Whimsy. Write 2-3 immersive paragraphs describing the following deterministic outcome.
Character: ${charName}
Location: ${loc}
Action Taken: ${actionText}
Clocks Advanced: ${JSON.stringify(outcome.clocks_advanced || [])}
Stat Changes: ${JSON.stringify(outcome.effects || [])}
Choices Offered: ${JSON.stringify(outcome.offered_choices || [])}
Strict rule: Do not alter the game state numbers or outcomes. Only write the sensory narrative and list the offered choices under [OPTIONS].`;
    }
  }

  const localInstance = new LocalNarrator();

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      LocalNarrator,
      localNarrator: localInstance
    };
  }

  if (typeof window !== 'undefined') {
    window.LocalNarrator = LocalNarrator;
    window.localNarrator = localInstance;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
