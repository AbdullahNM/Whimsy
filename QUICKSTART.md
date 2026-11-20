# Whimsy CYOA Engine — Quickstart Guide

This guide walks you through setting up and running the Whimsy Choice-Based Narrative / CYOA Engine. Choose the execution method that best fits your workflow:

1. **[Method 1: Docker Compose](#method-1-docker-compose-recommended)** — One-command setup for engine and UI with isolated dependencies.
2. **[Method 2: Direct Local Execution](#method-2-direct-local-execution-native-python--nodejs)** — Run natively with Python 3.10+ and Node.js 18+.
3. **[Method 3: Browser Standalone / Dist Build](#method-3-browser-standalone--dist-build-zero-backend-offline-mode)** — Zero-backend, 100% offline single-file HTML bundle.

---

## Overview & Prerequisites

### System Requirements

| Execution Method | Prerequisites |
|---|---|
| **Docker Compose** *(Recommended)* | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Docker Compose v2+ |
| **Native Execution** | **Python 3.10+**, **Node.js 18+** *(Node is only needed for the JS test suite)*, and `git` |
| **Browser Standalone Build** | **Python 3.10+** (to build) + any modern web browser (to play) |

---

## Method 1: Docker Compose (Recommended)

Docker Compose provides a complete, containerized environment launching both the backend Engine server and the PWA frontend with a single command.

### 1. Start the Containers

From the repository root:

```bash
docker compose up --build
```

To run in the background (detached mode):

```bash
docker compose up -d --build
```

### 2. Access the Application

- **Frontend PWA:** [http://localhost:3000](http://localhost:3000)
- **Engine API Server:** [http://localhost:8000](http://localhost:8000)
- **Engine Health Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)

### 3. Campaign Data Persistence

The `docker-compose.yml` mounts the host's `./CAMPAIGNS` directory into the container:

```yaml
volumes:
  - ./CAMPAIGNS:/app/CAMPAIGNS
```

All turn saves, living machine states (`status.json`), Markdown logs (`status.md`), inventories, relationships, and newly created campaigns are persisted directly onto your host filesystem across container restarts and image rebuilds.

### 4. Viewing Logs

Stream container logs in real time:

```bash
# View all service logs
docker compose logs -f

# View only engine or UI logs
docker compose logs -f engine
docker compose logs -f ui
```

### 5. Stopping the Containers

To cleanly stop the services:

```bash
docker compose down
```

---

## Method 2: Direct Local Execution (Native Python + Node.js)

For local development, hacking on the engine, or running unit test suites directly.

### Step 1: Clone the Repository

```bash
git clone https://github.com/AbdullahNM/Whimsy.git
cd Whimsy
```

### Step 2: Set Up Virtual Environment

Create and activate a Python virtual environment:

- **macOS / Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

- **Windows (Command Prompt):**
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```

### Step 3: Install Dependencies

Install the required Python packages defined in `requirements.txt`:

```bash
pip install -r requirements.txt
```

*(Core dependencies: `jsonschema>=4.20.0`, `pyyaml>=6.0`)*

### Step 4: Start Engine Server

Run the core turn generation engine:

```bash
python ENGINE/engine.py
```

- Server starts on `http://localhost:8000`.
- Verify engine health: [http://localhost:8000/health](http://localhost:8000/health)
- To customize the port, export `ANTIGRAVITY_PORT` (e.g. `export ANTIGRAVITY_PORT=8080`).

### Step 5: Start PWA Frontend

In a separate terminal window or tab, serve the `UI` directory using Python's built-in HTTP server:

```bash
python -m http.server 3000 --directory UI
```

Open your browser to:
[http://localhost:3000](http://localhost:3000)

### Step 6: Running the Test Suites

Execute the comprehensive automated test suites:

- **Python Tests (Unittest):**
  ```bash
  python -m unittest discover -s tests
  ```

- **JavaScript / UI Tests (Node.js test runner):**
  ```bash
  node --test tests/*.js
  ```

- **All-in-One Test Script:**
  ```bash
  bash tests/run_all_tests.sh
  ```

---

## Method 3: Browser Standalone / Dist Build (Zero-Backend Offline Mode)

Whimsy features a pure browser runtime that compiles entire campaigns into a self-contained, single-file HTML package with zero external backend dependencies. It runs completely offline using browser IndexedDB and inlined deterministic game logic.

### 1. Build a Distributable Campaign Package

Run the distribution build script targeting a campaign:

```bash
python scripts/build_dist.py --campaign template_campaign
```

This compiles:
- `dist/template_campaign/index.html` — Standalone playable HTML5 file with inlined runtime, CSS, and manifest.
- `dist/template_campaign/template_campaign.zip` — Itch.io-ready HTML5 upload bundle.
- `dist/template_campaign/itch_metadata.json` & `ITCH_LISTING.md` — Storefront listing assets.

### 2. Launch Offline

Simply double-click or open `dist/template_campaign/index.html` in any modern web browser. No web server, Docker daemon, or Python runtime is required at play time.

---

## Configuration & Environment Variables

The Engine and Docker setup support the following environment variables:

| Variable | Default | Scope | Description |
|---|---|---|---|
| `ANTIGRAVITY_PORT` | `8000` | Engine / Docker | Port number the Python Engine HTTP server binds to. |
| `PYTHONUNBUFFERED` | `1` | Engine / Docker | Forces stdout and stderr streams to be unbuffered for instant console logging. |
| `WHIMSY_MODEL` | *(unset)* | Engine | Model identifier to override the default LLM model for cloud generation. |
| `OPENROUTER_API_KEY` | *(unset)* | Engine | API key for OpenRouter LLM completions (Tier 3 live generation). |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | Engine | Target model identifier when using OpenRouter. |
| `GEMINI_API_KEY` | *(unset)* | Engine | API key for Google Gemini completions. |
| `WHIMSY_CHANNEL_MODE` | `auto` | Engine | Agent channel routing mode (`auto`, `direct`, `mock`). |

---

## Troubleshooting

### Port 8000 or Port 3000 Already in Use

- **Symptom:** `OSError: [Errno 98] Address already in use` or Docker container fails with `bind: address already in use`.
- **Solution (Native):** Check which process is occupying the port and terminate it, or set a custom port:
  - *Windows:* `netstat -ano | findstr :8000` then `taskkill /PID <PID> /F`
  - *macOS/Linux:* `lsof -i :8000` then `kill -9 <PID>`
  - Override engine port: `ANTIGRAVITY_PORT=8080 python ENGINE/engine.py`
- **Solution (Docker):** Modify the host port mapping in `docker-compose.yml`, e.g., `"8080:8000"` for engine or `"3001:3000"` for UI.

### CORS & Network Connection Errors

- **Symptom:** UI displays network errors when dispatching actions or requesting `/generate`.
- **Solution:**
  1. Confirm the Engine server is running by navigating to [http://localhost:8000/health](http://localhost:8000/health). You should see `{"status":"ok", ...}`.
  2. If using Docker, ensure both `engine` and `ui` containers are running (`docker compose ps`).
  3. Ensure ad-blockers or browser privacy extensions are not intercepting cross-port requests between `localhost:3000` and `localhost:8000`.

### Campaign Volume Mounting & File Permissions

- **Symptom:** New turns or edits made in the container do not appear in host `./CAMPAIGNS`, or `PermissionError` occurs in container logs.
- **Solution:**
  1. Verify the `./CAMPAIGNS` folder exists locally on the host before running `docker compose up`.
  2. On Linux/macOS, ensure the directory permissions allow the container user to write:
     ```bash
     chmod -R u+rwX CAMPAIGNS
     ```
  3. Check container mount status:
     ```bash
     docker compose exec engine ls -la /app/CAMPAIGNS
     ```
