# Genre-Agnostic Campaign Schema

## Purpose
Defines standard JSON schemas for campaign configuration (`GLOBAL/SCHEMAS/campaign_init.schema.json`) and active turn state (`GLOBAL/SCHEMAS/turn_state.schema.json`), enabling arbitrary genre implementations (such as academic cultivation fantasy or cosmic mythology) through unified architectural contracts.

## Requirements

### Requirement: Campaign Initiation Schema Validation
The system SHALL validate all `campaign_config.json` files against `GLOBAL/SCHEMAS/campaign_init.schema.json`. Each campaign config must define `id`, `title`, `genre`, `theme`, `metrics`, `entity_header`, `status_sections`, and `sidebar`.

#### Scenario: Valid campaign configuration passes schema validation
- **WHEN** `campaign_config.json` is validated against `campaign_init.schema.json`
- **THEN** validation succeeds with zero schema errors.

#### Scenario: Missing required theme properties fail validation
- **WHEN** a `campaign_config.json` is missing required theme properties such as `bg_dark` or `gold_primary`
- **THEN** schema validation rejects the configuration.

### Requirement: Turn State Schema Compliance
The system SHALL validate all living campaign states (`GAMEPLAY/status.json`) against `GLOBAL/SCHEMAS/turn_state.schema.json`. Every status state must define `campaign_id`, `turn`, `timeline`, `progression` (including `checkpoint_tokens` and `checkpoint_max`), and `scene_anchor`.

#### Scenario: Living status JSON conforms to turn state schema
- **WHEN** `GAMEPLAY/status.json` for any active campaign is validated against `turn_state.schema.json`
- **THEN** validation succeeds with valid types and positive turn numbers.

### Requirement: Genre Neutrality and Metric Path Binding
The schema engine SHALL support diverse genre representations (including fantasy academy vitals, cosmic divinity pools, or noir sanity trackers) via dot-notation property paths bound to arbitrary JSON state structures.

#### Scenario: Bind fantasy academy metric paths
- **WHEN** configuration specifies `path: "progression.xp"` and `max_path: "progression.xp_threshold"`
- **THEN** the UI engine resolves and displays current experience against its threshold.

#### Scenario: Bind cosmic pantheon metric paths
- **WHEN** configuration specifies `path: "progression.divinity"` and `max_path: "progression.divinity_max"`
- **THEN** the UI engine resolves and displays cosmic divinity metrics without schema modifications.
