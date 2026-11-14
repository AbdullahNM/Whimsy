/**
 * UI/narrator/authored_narrator.js
 * ================================
 * Tier 1 Authored / Offline Narrator.
 *
 * Implements Issue #17 R1, R6 (Tier 1), R7:
 * - Always available, zero network required, keyless.
 * - Produces rich prose describing the deterministic outcome.
 * - Emits standard delimited receipts ([XP RESOLUTION], [CURRENCY RESOLUTION], [SYS])
 *   and formatted [OPTIONS] block matching outcome.offered_choices.
 */

(function (global) {
  'use strict';

  class AuthoredNarrator {
    constructor() {
      this.tier = 1;
      this.name = 'Authored / Offline';
    }

    /**
     * Generate narrative prose for a resolved turn outcome.
     * @param {Object} params
     * @param {string|Object} params.action - Player action taken
     * @param {Object} params.outcome - Outcome object from Core.resolve
     * @param {Object} params.context - Campaign context, character info, scene anchor
     * @returns {string} Fully rendered GM response markdown
     */
    generateNarrative({ action, outcome, context = {} }) {
      if (!outcome) {
        throw new Error('AuthoredNarrator requires a valid deterministic Outcome');
      }

      const actionText = typeof action === 'string'
        ? action
        : (action.text || (action.num ? `${action.num}. Choice` : 'Direct Action'));

      const nextState = outcome.next_state || {};
      const charName = nextState.character?.name || context.character?.name || 'You';
      const scene = nextState.scene_anchor || context.sceneAnchor || {};
      const loc = scene.location || 'Current Position';
      const timeStamp = scene.time || nextState.pacing_state?.timeline_stamp || '';
      const genre = context.genre || context.activeConfig?.genre || 'Atmospheric Adventure';

      // 1. Compose Narrative Action & Scene Beat
      const narrativeParagraphs = this._buildProse(actionText, outcome, charName, loc, timeStamp, genre, context);

      // 2. Format Receipt Blocks
      const receipts = this._buildReceipts(outcome, nextState);

      // 3. Format Options Block
      const optionsBlock = this._buildOptions(outcome.offered_choices || []);

      return [
        narrativeParagraphs.join('\n\n'),
        receipts,
        optionsBlock
      ].filter(Boolean).join('\n\n');
    }

    _buildProse(actionText, outcome, charName, loc, timeStamp, genre, context) {
      const paragraphs = [];
      const cleanAction = actionText.replace(/^\d+[\.\)]\s*/, '').replace(/\[RECAL:.*?\]/i, '').trim();

      // Opening paragraph: immediate somatic and spatial execution of the action
      let intro = `${charName} commits to the course: "${cleanAction}". Within ${loc}, the surrounding atmosphere responds in subtle shifts.`;
      if (timeStamp) {
        intro += ` By ${timeStamp}, the physical reality of the situation settles into place.`;
      }
      paragraphs.push(intro);

      // Middle paragraph: consequences, stat shifts, or clock pressures
      const clockAdvances = outcome.clocks_advanced || [];
      const effects = outcome.effects || [];
      const events = outcome.events || [];

      let consequenceDetails = [];

      for (const clk of clockAdvances) {
        if (clk.fired) {
          consequenceDetails.push(`Critical threshold reached: **${clk.label || clk.id}** triggers immediate consequences across the area.`);
        } else {
          consequenceDetails.push(`The passage of tension is palpable as **${clk.label || clk.id}** advances to ${clk.current}/${clk.max}.`);
        }
      }

      for (const ev of events) {
        consequenceDetails.push(`Event: ${ev}`);
      }

      for (const eff of effects) {
        if (eff.type === 'stat_change' && eff.delta !== 0) {
          const statName = eff.target.replace(/^progression\./, '').toUpperCase();
          const sign = eff.delta > 0 ? '+' : '';
          consequenceDetails.push(`${statName} shifts (${sign}${eff.delta}) to ${eff.current}.`);
        } else if (eff.type === 'location_change') {
          consequenceDetails.push(`Transitioning into new coordinates: ${eff.location}.`);
        }
      }

      if (consequenceDetails.length > 0) {
        paragraphs.push(consequenceDetails.join(' '));
      } else {
        paragraphs.push(`Every step demands measured focus. The path ahead remains taut with anticipation, requiring tactical clarity before the next move.`);
      }

      // Closing paragraph: transition to current situation
      const sceneCtx = sceneContextFromState(outcome.next_state) || context.upcomingHooks || '';
      if (sceneCtx) {
        const snippet = sceneCtx.split('\n')[0].replace(/^#+\s*/, '').trim();
        paragraphs.push(`Current situation: ${snippet}. The next juncture presents itself clearly.`);
      }

      return paragraphs;
    }

    _buildReceipts(outcome, nextState) {
      const receiptLines = [];

      // XP Resolution
      if (outcome.progression_delta && outcome.progression_delta.xp !== undefined) {
        const delta = outcome.progression_delta.xp;
        const current = nextState.progression?.xp || 0;
        const previous = current - delta;
        const sign = delta >= 0 ? `+${delta}` : `${delta}`;
        receiptLines.push(`[XP RESOLUTION: Previous: ${previous} | Delta: ${sign} | New Total: ${current}]`);
      }

      // Currency / Purse Resolution
      if (outcome.resources_delta && Object.keys(outcome.resources_delta).length > 0) {
        const purseDisplay = nextState.purse?.display || '';
        const deltas = Object.entries(outcome.resources_delta)
          .map(([k, v]) => `${v >= 0 ? '+' : ''}${v} ${k}`)
          .join(', ');
        receiptLines.push(`[CURRENCY RESOLUTION: Delta: ${deltas} | New Purse: ${purseDisplay}]`);
      }

      // System Delta / Clocks Block
      const sysParts = [];
      if (outcome.clocks_advanced && outcome.clocks_advanced.length > 0) {
        for (const clk of outcome.clocks_advanced) {
          sysParts.push(`Clock '${clk.label || clk.id}' -> ${clk.current}/${clk.max}${clk.fired ? ' [TRIGGERED]' : ''}`);
        }
      }
      if (outcome.effects) {
        for (const eff of outcome.effects) {
          if (eff.type === 'flag_set') {
            sysParts.push(`Flag set: ${eff.target} = ${eff.value}`);
          }
        }
      }

      if (sysParts.length > 0) {
        receiptLines.push(`[SYS: ${sysParts.join(' | ')}]`);
      }

      return receiptLines.join('\n');
    }

    _buildOptions(offeredChoices) {
      if (!offeredChoices || offeredChoices.length === 0) {
        return '';
      }

      const lines = ['[OPTIONS]'];
      for (const choice of offeredChoices) {
        lines.push(`${choice.index}. ${choice.text}`);
      }
      return lines.join('\n');
    }
  }

  function sceneContextFromState(state) {
    if (!state) return '';
    return state.scene_anchor?.context || state.public_state?.open_threads?.[0] || '';
  }

  const authoredInstance = new AuthoredNarrator();

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      AuthoredNarrator,
      authoredNarrator: authoredInstance
    };
  }

  if (typeof window !== 'undefined') {
    window.AuthoredNarrator = AuthoredNarrator;
    window.authoredNarrator = authoredInstance;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
