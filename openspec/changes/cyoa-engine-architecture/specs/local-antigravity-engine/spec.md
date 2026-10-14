## ADDED Requirements

### Requirement: Local HTTP Server and CORS Compliance
The local engine server (`ENGINE/engine.py`) SHALL run an HTTP server binding to a configurable port (default 8000) and return full CORS headers (`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`) on all requests, including HTTP OPTIONS preflight queries.

#### Scenario: Preflight OPTIONS request
- **WHEN** client sends an HTTP `OPTIONS` request to any endpoint
- **THEN** server responds with status code 204 and appropriate `Access-Control-Allow-*` headers.

#### Scenario: Health endpoint check
- **WHEN** client sends a `GET` request to `/health` or `/status`
- **THEN** server responds with status code 200 and a JSON payload containing `status: "online"`.

### Requirement: Deterministic Turn Generation and Receipt Calculation
The engine server SHALL handle `POST /generate` requests containing `action`, `campaign`, and `currentTurn`, producing narrative response text accompanied by formatted receipt blocks (`[XP RESOLUTION]`, `[CURRENCY RESOLUTION]`, `[SYS]`).

#### Scenario: Successful turn generation payload
- **WHEN** a valid POST payload is sent to `/generate`
- **THEN** the server returns a 200 response with generated narrative and valid resolution blocks.

#### Scenario: Invalid JSON payload handling
- **WHEN** an unparseable body is POSTed to `/generate`
- **THEN** the server responds with status code 400 and an informative error message.

### Requirement: Fallback Numbered Choices Generation
When generating turn outcomes, the engine SHALL append a formatted options block `### [OPTIONS & TYPABLE REFERENCE]` containing 4 distinct, numbered tactical choices for the player.

#### Scenario: Numbered choice block formatting
- **WHEN** turn generation completes
- **THEN** the response includes numbered options from 1 through 4 formatted for direct player selection.
