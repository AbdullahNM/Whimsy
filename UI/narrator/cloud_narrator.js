/**
 * UI/narrator/cloud_narrator.js
 * =============================
 * Tier 3 Cloud LLM Narrator (BYO API Key via Gemini or OpenRouter).
 *
 * Implements Issue #17 R6 (Tier 3), R7, R8:
 * - Uses BYO API key for Gemini direct or OpenRouter.
 * - Prompts model with outcome constraints ensuring narrative matches deterministic Core.resolve.
 * - Enforces timeout protection and non-blocking fallback (R8).
 */

(function (global) {
  'use strict';

  class CloudNarrator {
    constructor() {
      this.tier = 3;
      this.name = 'Cloud LLM (BYO API Key)';
      this.defaultTimeoutMs = 15000;
    }

    /**
     * Determine if cloud narration is configured.
     */
    isConfigured(apiKey = null) {
      if (apiKey && typeof apiKey === 'string' && apiKey.trim().length > 5) {
        return true;
      }
      if (typeof localStorage !== 'undefined') {
        const stored = localStorage.getItem('gemini_api_key');
        return Boolean(stored && stored.trim().length > 5);
      }
      return false;
    }

    /**
     * Generate narrative prose using cloud LLM.
     */
    async generateNarrative({
      action,
      outcome,
      context = {},
      apiKey = null,
      model = null,
      pacing = 'standard',
      timeoutMs = null
    }) {
      if (!outcome) {
        throw new Error('CloudNarrator requires a valid deterministic Outcome');
      }

      const key = apiKey || (typeof localStorage !== 'undefined' ? localStorage.getItem('gemini_api_key') : null);
      if (!key) {
        throw new Error('No Cloud API key configured.');
      }

      const selectedModel = model || (typeof localStorage !== 'undefined' ? localStorage.getItem('cyoa_model') : 'gemini-2.5-flash');
      const timeout = timeoutMs || this.defaultTimeoutMs;
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      let timer = null;

      try {
        if (controller) {
          timer = setTimeout(() => controller.abort(), timeout);
        }

        const prompt = this._buildPrompt(action, outcome, context, pacing);
        let narrative = '';

        if (key.startsWith('sk-or-') || (selectedModel && selectedModel.startsWith('openrouter/'))) {
          // OpenRouter API
          narrative = await this._callOpenRouter(key, selectedModel, prompt, controller);
        } else {
          // Gemini API Direct
          narrative = await this._callGemini(key, selectedModel, prompt, controller);
        }

        if (timer) clearTimeout(timer);
        return narrative.trim();
      } catch (err) {
        if (timer) clearTimeout(timer);
        if (err.name === 'AbortError') {
          throw new Error(`Cloud LLM timed out after ${timeout}ms`);
        }
        throw err;
      }
    }

    async _callOpenRouter(apiKey, modelName, prompt, controller) {
      const actualModel = modelName.startsWith('openrouter/') ? modelName.replace('openrouter/', '') : modelName;
      const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': typeof window !== 'undefined' ? window.location.origin : 'https://github.com/AbdullahNM/Whimsy',
          'X-Title': 'Whimsy CYOA Engine'
        },
        body: JSON.stringify({
          model: actualModel,
          messages: [
            { role: 'system', content: 'You are an evocative, literary Game Master for an interactive CYOA campaign.' },
            { role: 'user', content: prompt }
          ],
          temperature: 0.7,
          max_tokens: 600
        }),
        signal: controller ? controller.signal : undefined
      });

      if (!res.ok) {
        throw new Error(`OpenRouter returned HTTP ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) throw new Error('OpenRouter returned empty message content');
      return content;
    }

    async _callGemini(apiKey, modelName, prompt, controller) {
      const cleanModel = modelName.includes('/') ? modelName.split('/').pop() : modelName;
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${cleanModel}:generateContent?key=${apiKey}`;

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            temperature: 0.7,
            maxOutputTokens: 600
          }
        }),
        signal: controller ? controller.signal : undefined
      });

      if (!res.ok) {
        throw new Error(`Gemini API returned HTTP ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      const content = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!content) throw new Error('Gemini API returned empty text');
      return content;
    }

    _buildPrompt(action, outcome, context, pacing) {
      const nextState = outcome.next_state || {};
      const actionText = typeof action === 'string' ? action : (action.text || '');
      const charName = nextState.character?.name || context.character?.name || 'The protagonist';
      const loc = nextState.scene_anchor?.location || 'Unknown Area';

      let pacingNote = 'Write 2 to 3 balanced paragraphs of sensory narrative prose.';
      if (pacing === 'concise') pacingNote = 'Write 1 to 2 short, punchy paragraphs.';
      if (pacing === 'expansive') pacingNote = 'Write 3 to 4 detailed, atmospheric paragraphs with character introspection.';

      const choicesText = (outcome.offered_choices || [])
        .map(c => `${c.index}. ${c.text}`)
        .join('\n');

      return `You are the Game Master. Write the narrative resolution for this turn.
${pacingNote}

Protagonist: ${charName}
Location: ${loc}
Action Taken: ${actionText}

Deterministic State Outcome (MUST be respected):
- Clocks Advanced: ${JSON.stringify(outcome.clocks_advanced || [])}
- Progression Delta: ${JSON.stringify(outcome.progression_delta || {})}
- Resource Delta: ${JSON.stringify(outcome.resources_delta || {})}
- Events Triggered: ${JSON.stringify(outcome.events || [])}

At the end of your prose, you MUST append:
[OPTIONS]
${choicesText}

Do not contradict the deterministic outcome numbers.`;
    }
  }

  const cloudInstance = new CloudNarrator();

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      CloudNarrator,
      cloudNarrator: cloudInstance
    };
  }

  if (typeof window !== 'undefined') {
    window.CloudNarrator = CloudNarrator;
    window.cloudNarrator = cloudInstance;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
