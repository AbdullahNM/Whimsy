/**
 * UI/core/deterministic_core.js
 * =============================
 * Pure headless browser-runnable deterministic turn resolution core.
 * Browser-side implementation of Core.resolve producing byte-identical
 * Outcome JSON for identical input compared with Python ENGINE/deterministic_core.py.
 *
 * Adheres strictly to Issue #14: R1, R2, R4, R5, R7.
 */

class ActionValidationError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ActionValidationError';
  }
}

class TransitionRejectedError extends Error {
  constructor(message) {
    super(message);
    this.name = 'TransitionRejectedError';
  }
}

/**
 * 32-bit PRNG (Mulberry32) for cross-language parity with Python.
 */
class SeededRNG {
  constructor(seed = 0) {
    this.state = seed >>> 0;
  }

  next() {
    this.state = (this.state + 0x6D2B79F5) >>> 0;
    let z = this.state;
    z = Math.imul(z ^ (z >>> 15), z | 1) >>> 0;
    z = (z ^ (z + Math.imul(z ^ (z >>> 7), z | 61))) >>> 0;
    return ((z ^ (z >>> 14)) >>> 0) / 4294967296;
  }

  randint(a, b) {
    return a + Math.floor(this.next() * (b - a + 1));
  }
}

function sortKeys(value) {
  if (Array.isArray(value)) {
    return value.map(sortKeys);
  } else if (value !== null && typeof value === 'object') {
    const sorted = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = sortKeys(value[key]);
    }
    return sorted;
  }
  return value;
}

class Outcome {
  constructor({
    effects = [],
    events = [],
    clocks_advanced = [],
    progression_delta = {},
    resources_delta = {},
    offered_choices = [],
    next_state = {},
    version = 1
  } = {}) {
    this.effects = effects;
    this.events = events;
    this.clocks_advanced = clocks_advanced;
    this.progression_delta = progression_delta;
    this.resources_delta = resources_delta;
    this.offered_choices = offered_choices;
    this.next_state = next_state;
    this.version = version;
  }

  toDict() {
    return {
      version: this.version,
      effects: this.effects,
      events: this.events,
      clocks_advanced: this.clocks_advanced,
      progression_delta: this.progression_delta,
      resources_delta: this.resources_delta,
      offered_choices: this.offered_choices,
      next_state: this.next_state
    };
  }

  toJson(indent = 2) {
    return JSON.stringify(sortKeys(this.toDict()), null, indent);
  }

  static fromDict(data) {
    return new Outcome({
      effects: data.effects || [],
      events: data.events || [],
      clocks_advanced: data.clocks_advanced || [],
      progression_delta: data.progression_delta || {},
      resources_delta: data.resources_delta || {},
      offered_choices: data.offered_choices || [],
      next_state: data.next_state || {},
      version: data.version !== undefined ? data.version : 1
    });
  }

  static fromJson(jsonStr) {
    return Outcome.fromDict(JSON.parse(jsonStr));
  }
}

const ZOOM_DETAILED_SCENE = 'detailed_scene';
const ZOOM_SHORT_SUMMARY = 'short_summary';
const ZOOM_MONTAGE = 'montage';
const ZOOM_TIME_SKIP = 'time_skip';
const VALID_ZOOM_LEVELS = [ZOOM_DETAILED_SCENE, ZOOM_SHORT_SUMMARY, ZOOM_MONTAGE, ZOOM_TIME_SKIP];

const DEFAULT_FALLBACK_CHOICES = [
  {
    index: 1,
    text: 'Press forward along your primary path.'
  },
  {
    index: 2,
    text: 'Inspect your immediate environment for hidden clues or resources.'
  },
  {
    index: 3,
    text: 'Confer with your companions to consolidate strategy.'
  },
  {
    index: 4,
    text: 'Rest and recover your somatic vitals before proceeding.'
  }
];

class Core {
  static resolve(state, action, config = null, rng = null) {
    if (!state || typeof state !== 'object') {
      throw new Error('state must be a dictionary');
    }

    config = config || {};

    let rngInst;
    if (rng === null || rng === undefined) {
      const seed = config.seed !== undefined ? config.seed : 42;
      rngInst = new SeededRNG(seed);
    } else if (typeof rng === 'number') {
      rngInst = new SeededRNG(rng);
    } else {
      rngInst = rng;
    }

    // STEP 1: Action Validation (Precondition - R7)
    const { isValid, errorMsg, parsedAction } = this.validateAction(state, action, config);
    if (!isValid) {
      throw new ActionValidationError(errorMsg);
    }

    const mode = parsedAction.mode || 'classic_cyoa';
    const selectedIndex = parsedAction.index;
    const actionText = parsedAction.text || String(action);

    // STEP 2: Transition Gate Validation (Precondition)
    const pacingState = JSON.parse(JSON.stringify(state.pacing_state || {}));
    const proposedZoom = config.proposed_zoom || this.evaluateFocus(actionText, pacingState);
    let proposedIntensity = config.proposed_intensity;
    if (proposedIntensity === undefined || proposedIntensity === null) {
      proposedIntensity = this.recommendIntensity(actionText, pacingState);
    } else {
      proposedIntensity = parseInt(proposedIntensity, 10);
    }

    const proposedTimeSkip = parseInt(config.proposed_time_skip_minutes || 0, 10);
    const proposedLocation = config.proposed_location || null;
    const causalJustification = Boolean(config.causal_justification);
    const explicitPermission = Boolean(config.explicit_permission);

    const { isTransValid, transReason } = this.validateTransition(
      pacingState,
      actionText,
      proposedZoom,
      proposedTimeSkip,
      proposedIntensity,
      proposedLocation,
      causalJustification,
      explicitPermission
    );
    if (!isTransValid) {
      throw new TransitionRejectedError(transReason);
    }

    // STEP 3: Rule Evaluation & Mechanical Mutation Resolution
    const rules = config.rules || [];
    const matchedRule = this._matchRule(rules, selectedIndex, actionText);

    const effects = [];
    const events = [];
    const clocksAdvanced = [];

    let progressionDelta = {};
    let resourcesDelta = {};
    let ruleClocks = [];
    let flagsToSet = {};
    let timeDelta = 10;
    let zoomLevel = proposedZoom;
    let narrativeIntensity = proposedIntensity;
    let nextLocation = proposedLocation;
    let nextContext = null;
    let ruleNextChoices = null;

    if (matchedRule) {
      progressionDelta = Object.assign({}, matchedRule.progression_delta || {});
      resourcesDelta = Object.assign({}, matchedRule.resources_delta || {});
      ruleClocks = (matchedRule.clocks_advanced || []).slice();
      const ruleEvents = matchedRule.events || [];
      for (const e of ruleEvents) {
        events.push(e);
      }
      flagsToSet = Object.assign({}, matchedRule.flags || {});
      timeDelta = parseInt(matchedRule.time_delta_minutes !== undefined ? matchedRule.time_delta_minutes : 10, 10);
      zoomLevel = matchedRule.zoom_level || proposedZoom;
      narrativeIntensity = parseInt(matchedRule.narrative_intensity !== undefined ? matchedRule.narrative_intensity : proposedIntensity, 10);
      nextLocation = matchedRule.location || null;
      nextContext = matchedRule.context || null;
      ruleNextChoices = matchedRule.next_choices || null;
    } else {
      if (proposedTimeSkip > 0) {
        timeDelta = proposedTimeSkip;
      } else if (proposedZoom === ZOOM_TIME_SKIP) {
        timeDelta = 480;
      } else if (proposedZoom === ZOOM_MONTAGE) {
        timeDelta = 1440;
      } else if (selectedIndex === 4) {
        timeDelta = 60;
      } else if (selectedIndex === 2 || selectedIndex === 3) {
        timeDelta = 15;
      } else if (proposedZoom === ZOOM_SHORT_SUMMARY) {
        timeDelta = 30;
      } else {
        timeDelta = 10;
      }

      if (selectedIndex === 1) {
        zoomLevel = config.proposed_zoom ? config.proposed_zoom : ZOOM_DETAILED_SCENE;
        narrativeIntensity = config.proposed_intensity !== undefined && config.proposed_intensity !== null ? parseInt(config.proposed_intensity, 10) : 2;
        if (state.progression && 'energy' in state.progression) {
          progressionDelta.energy = -5;
        }
        flagsToSet.path_pressed = true;
        ruleClocks.push({ id: 'contract_deadline', delta: 1 });
      } else if (selectedIndex === 2) {
        zoomLevel = config.proposed_zoom ? config.proposed_zoom : ZOOM_DETAILED_SCENE;
        narrativeIntensity = config.proposed_intensity !== undefined && config.proposed_intensity !== null ? parseInt(config.proposed_intensity, 10) : 1;
        if (state.progression && 'energy' in state.progression) {
          progressionDelta.energy = -5;
        }
        if (state.progression && 'stress' in state.progression) {
          progressionDelta.stress = 2;
        }
        flagsToSet.inspected_area = true;
      } else if (selectedIndex === 3) {
        zoomLevel = config.proposed_zoom ? config.proposed_zoom : ZOOM_DETAILED_SCENE;
        narrativeIntensity = config.proposed_intensity !== undefined && config.proposed_intensity !== null ? parseInt(config.proposed_intensity, 10) : 1;
        if (state.progression && 'stress' in state.progression) {
          progressionDelta.stress = -5;
        }
        flagsToSet.conferred_with_companions = true;
      } else if (selectedIndex === 4) {
        zoomLevel = config.proposed_zoom ? config.proposed_zoom : ZOOM_SHORT_SUMMARY;
        narrativeIntensity = config.proposed_intensity !== undefined && config.proposed_intensity !== null ? parseInt(config.proposed_intensity, 10) : 1;
        if (state.progression && 'energy' in state.progression) {
          progressionDelta.energy = 25;
        }
        if (state.progression && 'stress' in state.progression) {
          progressionDelta.stress = -15;
        }
        flagsToSet.rested = true;
        ruleClocks.push({ id: 'contract_deadline', delta: 1 });
      }
    }

    // Clone state into nextState
    const nextState = JSON.parse(JSON.stringify(state));
    const currentTurn = parseInt(state.turn !== undefined ? state.turn : 1, 10);
    const nextTurn = currentTurn + 1;
    nextState.turn = nextTurn;
    effects.push({
      type: 'turn_advance',
      previous: currentTurn,
      current: nextTurn
    });

    // Apply progression mutations
    if (Object.keys(progressionDelta).length > 0) {
      if (!nextState.progression) nextState.progression = {};
      const keys = Object.keys(progressionDelta).sort();
      for (const key of keys) {
        if (key in nextState.progression) {
          const delta = progressionDelta[key];
          const oldVal = nextState.progression[key];
          const maxKey = `${key}_max`;
          const maxVal = nextState.progression[maxKey];
          let newVal = oldVal + delta;
          if (maxVal !== undefined && typeof maxVal === 'number') {
            newVal = Math.min(maxVal, newVal);
          }
          newVal = Math.max(0, newVal);
          nextState.progression[key] = newVal;
          effects.push({
            type: 'stat_change',
            target: `progression.${key}`,
            delta,
            previous: oldVal,
            current: newVal
          });
        }
      }
    }

    // Apply resources mutations
    if (Object.keys(resourcesDelta).length > 0) {
      if (!nextState.purse) nextState.purse = {};
      const keys = Object.keys(resourcesDelta).sort();
      for (const key of keys) {
        if (key in nextState.purse && typeof nextState.purse[key] === 'number') {
          const delta = resourcesDelta[key];
          const oldVal = nextState.purse[key];
          const newVal = Math.max(0, oldVal + delta);
          nextState.purse[key] = newVal;
          effects.push({
            type: 'resource_change',
            target: `purse.${key}`,
            delta,
            previous: oldVal,
            current: newVal
          });
        }
      }

      if ('credits' in nextState.purse) {
        nextState.purse.display = `${nextState.purse.credits} ₡`;
      } else if (['gold', 'silver', 'copper'].some(c => c in nextState.purse)) {
        const g = nextState.purse.gold || 0;
        const s = nextState.purse.silver || 0;
        const c = nextState.purse.copper || 0;
        nextState.purse.display = `${g}G ${s}S ${c}C`;
      }
    }

    // Apply flags
    if (Object.keys(flagsToSet).length > 0) {
      if (!nextState.public_state) nextState.public_state = {};
      if (!nextState.public_state.flags) nextState.public_state.flags = {};
      const keys = Object.keys(flagsToSet).sort();
      for (const k of keys) {
        const v = flagsToSet[k];
        nextState.public_state.flags[k] = v;
        effects.push({
          type: 'flag_set',
          target: `public_state.flags.${k}`,
          value: v
        });
      }
    }

    // Apply clocks
    if (!nextState.clocks) nextState.clocks = [];
    const clockMap = new Map();
    for (const c of nextState.clocks) {
      if (c.id) clockMap.set(c.id, c);
    }

    for (const rc of ruleClocks) {
      const cid = rc.id;
      const cdelta = parseInt(rc.delta !== undefined ? rc.delta : 1, 10);
      if (clockMap.has(cid)) {
        const c = clockMap.get(cid);
        const oldVal = parseInt(c.current || 0, 10);
        const maxVal = parseInt(c.max || 4, 10);
        const newVal = Math.min(maxVal, oldVal + cdelta);
        c.current = newVal;
        const fired = (newVal >= maxVal);
        clocksAdvanced.push({
          id: cid,
          label: c.label || cid,
          delta: cdelta,
          previous: oldVal,
          current: newVal,
          max: maxVal,
          fired
        });
        effects.push({
          type: 'clock_advance',
          target: `clocks.${cid}`,
          delta: cdelta,
          previous: oldVal,
          current: newVal,
          max: maxVal
        });
        if (fired && oldVal < maxVal) {
          events.push(`Clock filled: ${c.label || cid}`);
        }
      }
    }

    // Advance time and pacing
    if (!nextState.pacing_state) nextState.pacing_state = {};
    const pacing = nextState.pacing_state;
    const startMin = parseInt(pacing.elapsed_time_minutes || 0, 10);
    const endMin = startMin + timeDelta;
    pacing.elapsed_time_minutes = endMin;
    pacing.zoom_level = zoomLevel;
    pacing.narrative_intensity = narrativeIntensity;

    const oldStamp = pacing.timeline_stamp || 'Day 1, 08:00';
    const newStamp = this.advanceTimelineStamp(oldStamp, startMin, endMin, timeDelta);
    pacing.timeline_stamp = newStamp;

    if (nextLocation) {
      pacing.current_location = nextLocation;
      if (!nextState.scene_anchor) nextState.scene_anchor = {};
      nextState.scene_anchor.location = nextLocation;
    }

    if (nextContext) {
      if (!nextState.scene_anchor) nextState.scene_anchor = {};
      nextState.scene_anchor.context = nextContext;
    }

    effects.push({
      type: 'time_advance',
      delta_minutes: timeDelta,
      timeline_stamp: newStamp
    });

    // Check scheduled events crossed
    const scheduled = pacing.scheduled_events || [];
    for (const evt of scheduled) {
      const tt = parseInt(evt.trigger_time_minutes || 0, 10);
      const fired = Boolean(evt.fired);
      if (!fired) {
        if ((startMin < tt && tt <= endMin) || (startMin === 0 && tt === 0)) {
          evt.fired = true;
          events.push(`Scheduled event triggered: ${evt.description || evt.id}`);
        }
      }
    }

    // Offered choices for next turn
    let nextChoices;
    if (ruleNextChoices) {
      nextChoices = ruleNextChoices.map(c => Object.assign({}, c));
    } else {
      nextChoices = [
        {
          index: 1,
          text: 'Press forward along your primary path.'
        },
        {
          index: 2,
          text: 'Inspect your immediate environment for hidden clues or resources.'
        },
        {
          index: 3,
          text: 'Confer with your companions to consolidate strategy.'
        },
        {
          index: 4,
          text: 'Rest and recover your somatic vitals before proceeding.'
        }
      ];
    }

    nextState.offered_choices = nextChoices;

    return new Outcome({
      version: 1,
      effects,
      events,
      clocks_advanced: clocksAdvanced,
      progression_delta: progressionDelta,
      resources_delta: resourcesDelta,
      offered_choices: nextChoices,
      next_state: nextState
    });
  }

  static validateAction(state, action, config = null) {
    if (action === null || action === undefined) {
      return { isValid: false, errorMsg: 'Action input cannot be empty.', parsedAction: {} };
    }

    const cleanStr = String(action).trim();
    if (!cleanStr) {
      return { isValid: false, errorMsg: 'Action input cannot be empty.', parsedAction: {} };
    }

    config = config || {};
    let mode = config.operational_mode || state.operational_mode || config.mode || 'classic_cyoa';
    if (!['classic_cyoa', 'freeform_simulation'].includes(mode)) {
      mode = 'classic_cyoa';
    }

    if (mode === 'freeform_simulation') {
      return {
        isValid: true,
        errorMsg: '',
        parsedAction: {
          index: null,
          text: cleanStr,
          raw_input: action,
          mode: 'freeform_simulation'
        }
      };
    }

    const offeredChoices = state.offered_choices || config.offered_choices || config.choices || DEFAULT_FALLBACK_CHOICES;
    const choiceMap = new Map();
    for (const c of offeredChoices) {
      if (c && typeof c.index === 'number') {
        choiceMap.set(c.index, c);
      }
    }

    if (choiceMap.size === 0) {
      for (const c of DEFAULT_FALLBACK_CHOICES) {
        choiceMap.set(c.index, c);
      }
    }

    const indices = Array.from(choiceMap.keys()).sort((a, b) => a - b);
    const minIdx = indices[0];
    const maxIdx = indices[indices.length - 1];

    // Compound action detection
    const multiPattern = /^(?:option\s+|choice\s+)?(\d+)\s*(?:,|&|\band\b|\+|(?:and\s+)?then)\s*(?:option\s+|choice\s+)?(\d+)/i;
    if (multiPattern.test(cleanStr)) {
      return {
        isValid: false,
        errorMsg: 'Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.',
        parsedAction: {}
      };
    }

    const chainedPattern = /^(?:(?:option|choice)\s+)?\d+\s*[\.\)]?\s*(?:and\s+then|then|and|&|,|;|followed\s+by|\+)\s+(.+)$/i;
    if (chainedPattern.test(cleanStr)) {
      return {
        isValid: false,
        errorMsg: 'Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.',
        parsedAction: {}
      };
    }

    if (/\b(?:and\s+then|then\s+also|followed\s+by)\b/i.test(cleanStr)) {
      return {
        isValid: false,
        errorMsg: 'Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.',
        parsedAction: {}
      };
    }

    // Pure integer
    if (/^\d+$/.test(cleanStr)) {
      const idx = parseInt(cleanStr, 10);
      if (choiceMap.has(idx)) {
        return {
          isValid: true,
          errorMsg: '',
          parsedAction: {
            index: idx,
            text: choiceMap.get(idx).text,
            raw_input: action,
            mode: 'classic_cyoa'
          }
        };
      }
      return {
        isValid: false,
        errorMsg: `Option ${idx} is out of range. Valid options are ${minIdx} to ${maxIdx}.`,
        parsedAction: {}
      };
    }

    // Option or Choice prefix
    const optMatch = cleanStr.match(/^(?:option|choice)\s+(\d+)[\.\)]?$/i);
    if (optMatch) {
      const idx = parseInt(optMatch[1], 10);
      if (choiceMap.has(idx)) {
        return {
          isValid: true,
          errorMsg: '',
          parsedAction: {
            index: idx,
            text: choiceMap.get(idx).text,
            raw_input: action,
            mode: 'classic_cyoa'
          }
        };
      }
      return {
        isValid: false,
        errorMsg: `Option ${idx} is out of range. Valid options are ${minIdx} to ${maxIdx}.`,
        parsedAction: {}
      };
    }

    // Numbered prefix line
    const prefixMatch = cleanStr.match(/^(\d+)[\.\)]\s*(.*)$/);
    if (prefixMatch) {
      const idx = parseInt(prefixMatch[1], 10);
      const tail = prefixMatch[2].trim();
      if (choiceMap.has(idx)) {
        if (!tail || this._matchesChoiceText(tail, choiceMap.get(idx).text)) {
          return {
            isValid: true,
            errorMsg: '',
            parsedAction: {
              index: idx,
              text: choiceMap.get(idx).text,
              raw_input: action,
              mode: 'classic_cyoa'
            }
          };
        }
      }
    }

    // Semantic match against offered choices
    for (const idx of indices) {
      const targetText = choiceMap.get(idx).text || '';
      if (this._matchesChoiceText(cleanStr, targetText)) {
        return {
          isValid: true,
          errorMsg: '',
          parsedAction: {
            index: idx,
            text: targetText,
            raw_input: action,
            mode: 'classic_cyoa'
          }
        };
      }
    }

    return {
      isValid: false,
      errorMsg: 'Arbitrary freeform actions are not permitted in Classic CYOA mode. Please select one of the offered numbered options.',
      parsedAction: {}
    };
  }

  static _normalizeText(text) {
    if (!text) return '';
    const noBrackets = text.replace(/\[.*?\]/g, '');
    const cleaned = noBrackets.toLowerCase().replace(/[^\w\s]/g, ' ');
    return cleaned.split(/\s+/).filter(Boolean).join(' ');
  }

  static _matchesChoiceText(candidate, target) {
    const normCand = this._normalizeText(candidate);
    const normTarget = this._normalizeText(target);
    if (!normCand || !normTarget) return false;
    if (normCand === normTarget) return true;

    const parts = target.split(/[:\-–—]/);
    if (parts.length > 1) {
      const normTitle = this._normalizeText(parts[0]);
      if (normCand === normTitle) return true;
    }

    if (normCand.length >= 15 && normTarget.startsWith(normCand)) {
      return true;
    }

    return false;
  }

  static validateTransition(
    pacingState,
    actionText,
    proposedZoom,
    proposedTimeSkipMinutes,
    proposedIntensity,
    proposedLocation = null,
    causalJustification = false,
    explicitPermission = false
  ) {
    const pacing = pacingState || {};
    const currIntensity = parseInt(pacing.narrative_intensity !== undefined ? pacing.narrative_intensity : 1, 10);

    if (!VALID_ZOOM_LEVELS.includes(proposedZoom)) {
      return {
        isTransValid: false,
        transReason: `Proposed zoom level '${proposedZoom}' is invalid. Allowed: ${VALID_ZOOM_LEVELS.join(', ')}`
      };
    }

    const unresolved = pacing.unresolved_intentions || [];
    if (unresolved.length > 0 && !explicitPermission && !causalJustification) {
      if (proposedTimeSkipMinutes > 0 || proposedZoom === ZOOM_TIME_SKIP) {
        return {
          isTransValid: false,
          transReason: `Transition blocked: Scene has unresolved intentions (${unresolved.join(', ')}). Time skips and scene departures require explicit player resolution or causal justification.`
        };
      }
    }

    if ((proposedIntensity - currIntensity) > 2 && !causalJustification) {
      return {
        isTransValid: false,
        transReason: `Transition blocked: Dramatic escalation from intensity ${currIntensity} to ${proposedIntensity} exceeds the 2-step maximum without causal justification.`
      };
    }

    const currLoc = pacing.current_location;
    if (proposedLocation && currLoc && proposedLocation !== currLoc) {
      const hasConflicts = (pacing.active_conflicts || []).length > 0;
      if ((hasConflicts || unresolved.length > 0) && !causalJustification && !explicitPermission) {
        const actionLower = actionText.toLowerCase();
        const travelTerms = ['travel', 'journey', 'walk', 'ride', 'fly', 'sail', 'transit', 'head to', 'move to'];
        if (!travelTerms.some(t => actionLower.includes(t))) {
          return {
            isTransValid: false,
            transReason: `Transition blocked: Cannot jump location from '${currLoc}' to '${proposedLocation}' while active intentions or conflicts remain without travel action or causal justification.`
          };
        }
      }
    }

    return { isTransValid: true, transReason: 'Transition approved.' };
  }

  static evaluateFocus(actionText, pacingState = null) {
    const text = (actionText || '').toLowerCase().trim();

    const detailedCues = [
      /\bzoom in\b/, /\belaborate\b/, /\bin detail\b/, /\bin full detail\b/,
      /\bfocus on\b/, /\bstep by step\b/, /\bexamine closely\b/, /\blook closely\b/,
      /\btake my time\b/, /\bslow down\b/, /\bplay out\b/, /\bdetailed scene\b/
    ];
    if (detailedCues.some(p => p.test(text))) return ZOOM_DETAILED_SCENE;

    const timeSkipCues = [
      /\bskip to\b/, /\btime skip\b/, /\bskip ahead\b/, /\bfast forward\b/,
      /\bjump ahead\b/, /\bwait until morning\b/, /\bsleep until\b/,
      /\buntil tomorrow\b/, /\bnext morning\b/, /\bnext day\b/
    ];
    if (timeSkipCues.some(p => p.test(text))) return ZOOM_TIME_SKIP;

    const montageCues = [
      /\bmontage\b/, /\btraining montage\b/,
      /\bover the next (?:few|several) (?:days|weeks|months)\b/,
      /\bover the coming (?:days|weeks|months)\b/,
      /\bspend the next (?:few|several) (?:days|weeks|months)\b/
    ];
    if (montageCues.some(p => p.test(text))) return ZOOM_MONTAGE;

    const summaryCues = [
      /\bsummarize\b/, /\bshort summary\b/, /\bquick summary\b/,
      /\bbriefly\b/, /\bin short\b/, /\bgloss over\b/
    ];
    if (summaryCues.some(p => p.test(text))) return ZOOM_SHORT_SUMMARY;

    const conflictCues = [/\b(attack|strike|fight|shoot|slash|parry|dodge|block|cast|flee|ambush|confront|defend|stab|battle|grapple|duel)\b/];
    if (conflictCues.some(p => p.test(text))) return ZOOM_DETAILED_SCENE;

    const convCues = [/\b(talk|speak|ask|tell|discuss|confer|negotiate|interrogate|question|whisper|reply|say|inquire|persuade|interview|argue|plead)\b/];
    if (convCues.some(p => p.test(text))) return ZOOM_DETAILED_SCENE;

    const routineCues = [/\b(train|practice|drill|exercise|workout|conditioning|sparring|meditate|cultivate)\b/];
    if (routineCues.some(p => p.test(text))) {
      if (['days', 'weeks', 'months', 'daily'].some(t => text.includes(t))) return ZOOM_MONTAGE;
      return ZOOM_SHORT_SUMMARY;
    }

    const travelCues = [/\b(travel|journey|embark|transit|voyage|trek|march|commute|sail|fly|hike|walk to|ride to|head to)\b/];
    if (travelCues.some(p => p.test(text))) {
      if (['days', 'weeks', 'months', 'miles'].some(t => text.includes(t))) return ZOOM_MONTAGE;
      return ZOOM_SHORT_SUMMARY;
    }

    const downtimeCues = [/\b(rest|sleep|wait|pass time|downtime|work the shift|do chores|eat dinner|meals)\b/];
    if (downtimeCues.some(p => p.test(text))) return ZOOM_SHORT_SUMMARY;

    return ZOOM_DETAILED_SCENE;
  }

  static recommendIntensity(actionText, pacingState = null) {
    const text = (actionText || '').toLowerCase();
    const currIntensity = parseInt((pacingState && pacingState.narrative_intensity !== undefined) ? pacingState.narrative_intensity : 1, 10);

    const highStakes = ['ambush', 'explosion', 'assassination', 'life or death', 'mortal danger', 'catastrophe', 'critical failure', 'boss fight', 'last stand'];
    if (highStakes.some(w => text.includes(w))) return Math.min(5, currIntensity + 2);

    const activeCombat = ['attack', 'fight', 'shoot', 'flee', 'strike', 'battle', 'pursue', 'clash'];
    if (activeCombat.some(w => text.includes(w))) return Math.max(3, Math.min(4, currIntensity + 1));

    const tensionCues = ['interrogate', 'stealth', 'sneak', 'infiltrate', 'threaten', 'confront', 'alarm'];
    if (tensionCues.some(w => text.includes(w))) return currIntensity <= 2 ? 2 : 3;

    const routineCues = ['train', 'practice', 'travel', 'walk', 'eat', 'rest', 'sleep', 'study', 'read', 'downtime', 'chores', 'wait', 'confer', 'talk', 'discuss'];
    if (routineCues.some(w => text.includes(w))) return currIntensity <= 1 ? 1 : 2;

    return Math.max(1, Math.min(2, currIntensity));
  }

  static advanceTimelineStamp(oldStamp, startMin, endMin, deltaMin) {
    if (!oldStamp) {
      const day = 1 + Math.floor(endMin / 1440);
      const hh = String(Math.floor((endMin % 1440) / 60)).padStart(2, '0');
      const mm = String(endMin % 60).padStart(2, '0');
      return `Day ${day}, ${hh}:${mm}`;
    }

    const mDay = oldStamp.match(/Day\s+(\d+),\s*(\d{1,2}):(\d{2})/i);
    if (mDay) {
      const dayNum = parseInt(mDay[1], 10);
      const hour = parseInt(mDay[2], 10);
      const minute = parseInt(mDay[3], 10);
      const baseMinutes = (dayNum - 1) * 1440 + hour * 60 + minute;
      const newTotal = baseMinutes + deltaMin;
      const newDay = 1 + Math.floor(newTotal / 1440);
      const newHh = String(Math.floor((newTotal % 1440) / 60)).padStart(2, '0');
      const newMm = String(newTotal % 60).padStart(2, '0');
      return `Day ${newDay}, ${newHh}:${newMm}`;
    }

    const mClock = oldStamp.match(/^(\d{1,2}):(\d{2})(.*)$/);
    if (mClock) {
      const hour = parseInt(mClock[1], 10);
      const minute = parseInt(mClock[2], 10);
      const suffix = mClock[3];
      const totalClockMin = hour * 60 + minute + deltaMin;
      const newHh = String(Math.floor((totalClockMin % 1440) / 60)).padStart(2, '0');
      const newMm = String(totalClockMin % 60).padStart(2, '0');
      const daysPassed = Math.floor(totalClockMin / 1440);
      if (daysPassed > 0 && !suffix.includes('Day')) {
        return `Day ${1 + daysPassed}, ${newHh}:${newMm}${suffix}`;
      }
      return `${newHh}:${newMm}${suffix}`;
    }

    const day = 1 + Math.floor(endMin / 1440);
    const hh = String(Math.floor((endMin % 1440) / 60)).padStart(2, '0');
    const mm = String(endMin % 60).padStart(2, '0');
    return `Day ${day}, ${hh}:${mm}`;
  }

  static _matchRule(rules, choiceIndex, actionText) {
    for (const r of rules) {
      const m = r.match || {};
      if (m.choice_index !== undefined && choiceIndex !== null && choiceIndex !== undefined) {
        if (m.choice_index === choiceIndex) return r;
      }
      if (m.choice_text) {
        if (this._matchesChoiceText(actionText, m.choice_text)) return r;
      }
      if (m.action_regex) {
        const re = new RegExp(m.action_regex, 'i');
        if (re.test(actionText)) return r;
      }
    }
    return null;
  }
}

// Module export for Node.js / CommonJS and window global for browser
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    Core,
    Outcome,
    SeededRNG,
    ActionValidationError,
    TransitionRejectedError,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
    DEFAULT_FALLBACK_CHOICES
  };
}

if (typeof window !== 'undefined') {
  window.DeterministicCore = {
    Core,
    Outcome,
    SeededRNG,
    ActionValidationError,
    TransitionRejectedError,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
    DEFAULT_FALLBACK_CHOICES
  };
}
