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

  const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions';
  const FASTROUTER_URL = 'https://api.fastrouter.ai/api/v1/chat/completions';

  class CloudNarrator {
    constructor() {
      this.tier = 3;
      this.name = 'Cloud LLM (BYO API Key)';
      this.defaultTimeoutMs = 35000;
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

    _resolveProvider(key, modelName, provider = null, apiBaseUrl = null) {
      if (provider && ['openrouter', 'fastrouter', 'gemini', 'custom'].includes(provider)) {
        return provider;
      }
      if (apiBaseUrl && apiBaseUrl.includes('fastrouter.ai')) return 'fastrouter';
      if (apiBaseUrl && apiBaseUrl.includes('openrouter.ai')) return 'openrouter';
      if (apiBaseUrl) return 'custom';
      if (modelName && modelName.startsWith('fastrouter/')) return 'fastrouter';
      if (modelName && modelName.startsWith('openrouter/')) return 'openrouter';
      if (key && key.startsWith('sk-or-')) return 'openrouter';
      if (key && key.startsWith('AIza')) return 'gemini';
      if (modelName && modelName.startsWith('gemini') && !modelName.includes('/')) return 'gemini';
      return 'openrouter';
    }

    /**
     * Generate narrative prose using cloud LLM (OpenRouter, FastRouter, Gemini, or custom OpenAI-compatible).
     */
    async generateNarrative({
      action,
      outcome,
      context = {},
      apiKey = null,
      model = null,
      provider = null,
      apiBaseUrl = null,
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

      const selectedModel = model || (typeof localStorage !== 'undefined' ? localStorage.getItem('cyoa_model') : 'openrouter/anthropic/claude-3.5-sonnet');
      const storedProvider = provider || (typeof localStorage !== 'undefined' ? localStorage.getItem('cyoa_provider') : null);
      const storedBase = apiBaseUrl || (typeof localStorage !== 'undefined' ? localStorage.getItem('cyoa_api_base') : null);
      const resolvedProvider = this._resolveProvider(key, selectedModel, storedProvider, storedBase);

      const timeout = timeoutMs || this.defaultTimeoutMs;
      const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
      let timer = null;

      try {
        if (controller) {
          timer = setTimeout(() => controller.abort(), timeout);
        }

        const prompt = this._buildPrompt(action, outcome, context, pacing);
        let narrative = '';

        if (resolvedProvider === 'gemini') {
          narrative = await this._callGemini(key, selectedModel, prompt, controller);
        } else {
          const endpointUrl = storedBase || (resolvedProvider === 'fastrouter' ? FASTROUTER_URL : OPENROUTER_URL);
          const extraHeaders = resolvedProvider === 'openrouter'
            ? {
                'HTTP-Referer': typeof window !== 'undefined' ? window.location.origin : 'https://github.com/AbdullahNM/Whimsy',
                'X-Title': 'Whimsy CYOA Engine'
              }
            : {};
          narrative = await this._callOpenAICompatible(endpointUrl, key, selectedModel, prompt, controller, extraHeaders);
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

    async _callOpenAICompatible(url, apiKey, modelName, prompt, controller, extraHeaders = {}) {
      let actualModel = modelName || 'anthropic/claude-3.5-sonnet';
      if (actualModel.startsWith('openrouter/')) actualModel = actualModel.replace('openrouter/', '');
      if (actualModel.startsWith('fastrouter/')) actualModel = actualModel.replace('fastrouter/', '');
      if (actualModel === 'local-antigravity' || actualModel === 'local-endpoint') {
        actualModel = url.includes('fastrouter.ai') ? 'openai/gpt-4o-mini' : 'anthropic/claude-3.5-sonnet';
      }

      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          ...extraHeaders
        },
        body: JSON.stringify({
          model: actualModel,
          messages: [
            {
              role: 'system',
              content: 'You are the Active Game Master for Whimsy CYOA. Write grounded, sensory, plain-English prose (<=35 words per sentence), avoid STEM/calculus jargon and formulaic closings like "What will you do?", and obey Shadow Narrator channel directives.'
            },
            { role: 'user', content: prompt }
          ],
          temperature: 0.7,
          max_tokens: 750
        }),
        signal: controller ? controller.signal : undefined
      });

      if (!res.ok) {
        const errBody = await res.text().catch(() => res.statusText);
        throw new Error(`LLM endpoint returned HTTP ${res.status}: ${errBody.slice(0, 180)}`);
      }
      const data = await res.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) throw new Error('LLM endpoint returned empty message content');
      return content;
    }

    async _callOpenRouter(apiKey, modelName, prompt, controller) {
      return this._callOpenAICompatible(OPENROUTER_URL, apiKey, modelName, prompt, controller, {
        'HTTP-Referer': typeof window !== 'undefined' ? window.location.origin : 'https://github.com/AbdullahNM/Whimsy',
        'X-Title': 'Whimsy CYOA Engine'
      });
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
      const timeStamp = nextState.scene_anchor?.time || nextState.pacing_state?.timeline_stamp || '';

      let pacingNote = 'Write 2 to 3 balanced paragraphs of sensory narrative prose.';
      if (pacing === 'concise') pacingNote = 'Write 1 to 2 short, punchy paragraphs.';
      if (pacing === 'expansive') pacingNote = 'Write 3 to 4 detailed, atmospheric paragraphs with character dialogue.';

      const choicesText = (outcome.offered_choices || [])
        .map(c => `${c.index}. ${c.text}`)
        .join('\n');

      const extraSections = [];
      if (context.statusText) {
        extraSections.push(`Current Status Summary:\n${String(context.statusText).slice(0, 800)}`);
      }
      if (context.relationsText) {
        extraSections.push(`Social Standing:\n${String(context.relationsText).slice(0, 600)}`);
      }
      if (context.agentChannel && Array.isArray(context.agentChannel) && context.agentChannel.length > 0) {
        const latest = context.agentChannel.slice(-3).map(m => `[${m.sender} -> ${m.recipient}] ${m.content}`).join('\n');
        extraSections.push(`Shadow Narrator Channel Directives (MUST FOLLOW):\n${latest}`);
      }

      return `You are the Active Game Master for ${context.activeConfig?.title || 'this campaign'} (${context.genre || 'Interactive Fiction'}).
${pacingNote}
Style Contract: Natural everyday English, <=35 words per sentence, grounded physical sensory details, NO STEM/calculus jargon, NO formulaic endings ("What will you do?", "The choice is yours").

Protagonist: ${charName}
Location: ${loc}${timeStamp ? ` (${timeStamp})` : ''}
Action Taken: ${actionText}

${extraSections.join('\n\n')}

Deterministic State Outcome (MUST be respected):
- Next Turn: ${nextState.turn || 1}
- Clocks Advanced: ${JSON.stringify(outcome.clocks_advanced || [])}
- Progression Delta: ${JSON.stringify(outcome.progression_delta || {})}
- Resource Delta: ${JSON.stringify(outcome.resources_delta || {})}
- Events Triggered: ${JSON.stringify(outcome.events || [])}

At the end of your prose, you MUST append:
### [OPTIONS & TYPABLE REFERENCE]
${choicesText}

[SYS: Turn ${nextState.turn || 1} | Checkpoints: 5/5]

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
