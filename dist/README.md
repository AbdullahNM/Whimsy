# Whimsy itch.io Publishing & Distribution Runbook

> **Operational Runbook for Publishing Whimsy CYOA Campaigns to itch.io and HTML5 Web Distribution.**  
> This guide is executable by anyone releasing a Whimsy interactive fiction campaign.

---

## 1. Quick Start: Build Artifacts

To produce a self-contained distribution bundle for any campaign:

```bash
# 1. Build distribution package (playable HTML + itch.io zip archive)
python scripts/build_dist.py --campaign template_campaign

# 2. Or generate / refresh itch.io metadata separately
python scripts/itch_meta.py --campaign template_campaign
```

This generates the following artifacts in `dist/<campaign_id>/`:

| File | Description | itch.io Purpose |
|:-----|:------------|:----------------|
| `index.html` | Single self-contained playable game. All scripts, CSS, campaign data, and runtime inlined with zero external dependencies. | Used for direct browser play or local distribution. |
| `<id>.html` | Standalone named file identical to `index.html`. | Convenience copy for single-file sharing. |
| `<id>.zip` | Compressed zip archive containing `index.html` at its root. | **Primary upload artifact for itch.io HTML5 player**. |
| `itch_metadata.json` | Machine-readable metadata (title, tagline, description, tags, embed dimensions, pricing). | Reference and automation. |
| `ITCH_LISTING.md` | Pre-formatted itch.io store page listing and form field values. | Copy-paste directly into itch.io dashboard. |

---

## 2. Step-by-Step itch.io Publishing Guide

### Step 1: Create a New Project
1. Log in to [itch.io](https://itch.io) and navigate to **Create new project** (`https://itch.io/game/new`).
2. Open `dist/<campaign_id>/ITCH_LISTING.md` in your text editor alongside the browser.

### Step 2: Project Details
- **Title**: Copy `Title` from `ITCH_LISTING.md` (e.g. *New Campaign Universe*).
- **Project URL**: Auto-generated or customized slug (e.g. `https://your-name.itch.io/new-campaign-universe`).
- **Short description or tagline**: Copy tagline from `ITCH_LISTING.md` (kept under 100 characters).
- **Classification**: Select **Games**.
- **Kind of project**: Select **HTML** (*You have a ZIP or HTML file that will be played in the browser*).

### Step 3: Upload the Distribution Zip
1. In the **Uploads** section, click **Upload files**.
2. Select `dist/<campaign_id>/<campaign_id>.zip`.
3. Once uploaded, locate the uploaded file card and:
   - Check the box: **"This file will be played in the browser"**.
   - Set file display name (e.g. `Play in Browser (HTML5)`).
4. *(Optional)* Upload `dist/<campaign_id>/<campaign_id>.html` as an additional downloadable file if you want to allow players to download the standalone file for offline play.

### Step 4: Embed Options & Viewport Settings
Scroll to the **Embed options** section:
- **Viewport dimensions**:
  - **Width**: `1024` px
  - **Height**: `768` px
- **Responsive**: **Checked** (ensures UI scales gracefully across screen sizes).
- **Mobile friendly**: **Checked** (Whimsy's runtime is touch-optimized with 44px minimum touch targets and portrait/landscape adaptation).
- **Automatically start on page load**: **Checked**.
- **Fullscreen button**: **Checked** (allows immersive full-window play).
- **Scrollbars**: **Unchecked** (Whimsy manages its own interior scroll regions).

### Step 5: Pricing & Monetization Strategy
Whimsy is architected to support both free discovery and premium commercial monetization:

- **Recommended Default (Free-to-Play / PWYW)**:
  - In itch.io pricing, select **$0 or donate** (Pay What You Want).
  - Set suggested donation to **$2.99** or **$4.99**.
  - *Why this works:* itch.io data demonstrates that browser-first text IF achieves 5x–10x higher player conversion and community reviews when discovery is friction-free, with dedicated players donating via PWYW.
- **Paid / Premium Release**:
  - For full-length commercial campaigns (50+ turns, expansive lore), set pricing to **Paid** ($9.99–$19.99).
  - *itch.io Revenue Share:* itch.io lets creators set their own revenue share percentage (default 10%, can be adjusted to 0% or any preferred tier).
- **Demo Mode**:
  - Package a demo build containing Chapter 1 / prologue turns for browser play, with the full campaign packaged as a paid download or unlock.

### Step 6: Tags & Metadata
In the **Tags** section, paste the tags from `ITCH_LISTING.md`:
- Required discovery tags:
  ```
  interactive-fiction, text-based, cyoa, choice-matter, adventure, rpg
  ```
- Add genre-specific tags (e.g. `cyberpunk`, `sci-fi`, `fantasy`, `mystery`).

### Step 7: Description / Store Pitch
- Copy the **Store Page Description** markdown from `dist/<campaign_id>/ITCH_LISTING.md` and paste it into itch.io's description editor.
- The description outlines the campaign premise, consequence-driven mechanics, offline execution, and in-browser save persistence.

---

## 3. Post-Launch Discovery Channels

1. **Interactive Fiction Showcase**:
   - The itch.io **Interactive Fiction Showcase** is a year-long, non-competitive community event designed to surface text adventures, parser games, and CYOA.
   - Once your campaign is published, submit it to the showcase via its itch.io jam page.
2. **Visual Novel Database (VNDB)**:
   - For story-driven campaigns with character arcs and narrative focus, submit a listing to [VNDB](https://vndb.org).
   - Use tags: `Interactive Fiction`, `Choices Matter`, `Multiple Endings`, `Text-Heavy`.

---

## 4. Verification & QA Checklist

Before clicking "Public" on itch.io, test your build using the **Preview** button:

- [ ] **Instant Load**: The game boots immediately in the itch iframe without errors.
- [ ] **Turn 1 Execution**: Clicking choice 1 or typing a custom action resolves turn 2 cleanly.
- [ ] **Save Persistence**: Refresh the browser page (`F5`). Verify the campaign state and turn history restore from IndexedDB.
- [ ] **Mobile Layout**: Open dev tools device toolbar (or test on phone). Verify touch buttons are at least 44px tall and dossier tabs open cleanly.
- [ ] **Save Export/Import**: Click **⚙ Settings** $\rightarrow$ **Export Save JSON**. Verify file downloads.
- [ ] **Offline Play**: Disconnect network in dev tools; confirm turns continue resolving via Tier 1 (Authored Narrator).

---

## 5. R9 Private Campaign Safety & Git Hygiene

- Built artifacts under `dist/` (except this `README.md`) are ignored by git via `.gitignore`.
- Whimsy enforces **R9 (Private-campaign safety)** at build time:
  - Exactly one campaign is bundled per build.
  - Sibling campaign directories and private files under `CAMPAIGNS/` are prevented from leaking into the bundle.
  - Personal local paths (`C:\Users\...`, `/home/...`, `.git`, `.worktrees`) are strictly blocked.
- **Never commit private campaign distributions into public git repositories.**
