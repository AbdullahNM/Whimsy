## ADDED Requirements

### Requirement: Dynamic Top Bar Metric Synchronization
The client UI engine SHALL render floating metric pills in the top bar dynamically based on the active campaign's `metrics` configuration array, extracting values from `status.json` with regex fallback to Markdown text.

#### Scenario: Hydrate metrics from structured status JSON
- **WHEN** `extractMetrics` is invoked with valid `statusJson`
- **THEN** top bar metric elements `val-turn`, `val-xp`, `val-strain`, and `val-purse` are updated immediately with formatted values.

#### Scenario: Fallback to Markdown text parsing when JSON is unavailable
- **WHEN** `statusJson` is null and Markdown text contains `Strain: 4/10` and `Current Coin: 3G 6S 20C`
- **THEN** regex extraction parses and updates the corresponding metric pills accurately.

### Requirement: HUD Cards vs Living Record Markdown Views
The sidebar tabs SHALL render high-readability structured HUD cards when structured JSON data is available, while gracefully falling back to formatted Living Record Markdown views when JSON is missing or in legacy mode.

#### Scenario: Structured HUD rendering
- **WHEN** campaign configuration and `status.json` are loaded
- **THEN** `renderSchemaDrivenStatus` renders protagonist badges, progression bars, and stat boxes from schema.

#### Scenario: Markdown fallback view
- **WHEN** `status.json` is missing but `status.md` is present
- **THEN** `renderSchemaDrivenStatus` renders the raw Markdown content via `renderMarkdown`.

### Requirement: Responsive Mobile Drawer Navigation
The UI engine SHALL provide a responsive navigation drawer supporting mobile viewport constraints, toggling between collapsed and expanded states via the menu button.

#### Scenario: Toggle mobile sidebar drawer
- **WHEN** user clicks the sidebar toggle button on a mobile screen
- **THEN** the sidebar transitions between open and closed states without obstructing the story viewport.

### Requirement: Network-First Service Worker Caching
The client PWA SHALL register a service worker (`sw.js`) implementing a network-first caching strategy for dynamic files, falling back to cached assets for offline gameplay.

#### Scenario: Service worker offline fallback
- **WHEN** a client requests cached assets while offline
- **THEN** the service worker intercepts the request and responds with the cached copy.

#### Scenario: Bypass external API requests
- **WHEN** a request is made to external Gemini or LLM API endpoints
- **THEN** the service worker passes the request straight to the network without caching.
