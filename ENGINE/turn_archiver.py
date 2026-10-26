import os
import shutil
import glob
import re

MAX_ACTIVE_TURNS = 20
ACTIVE_BASELINE_TURNS = 15
ARCHIVE_BATCH_SIZE = 5

def get_turn_number(filename: str) -> int:
    match = re.search(r'turn_(\d+)', filename)
    return int(match.group(1)) if match else -1

def record_turn(campaign_dir: str, turn_number: int, player_input: str, gm_output: str, metadata: dict = None) -> str:
    active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
    archive_dir = os.path.join(campaign_dir, "TURNS", "ARCHIVE")
    os.makedirs(active_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # 1. Write current turn to its individual file
    turn_file = os.path.join(active_dir, f"turn_{turn_number:04d}.md")
    content = [
        f"# Turn {turn_number}",
        f"\n## Player Action\n{player_input}\n",
        f"## GM Response\n{gm_output}\n"
    ]
    if metadata:
        content.append(f"## System State Delta\n```json\n{metadata}\n```\n")

    with open(turn_file, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    # 2. Check for active turns reaching MAX_ACTIVE_TURNS threshold (batch archival)
    active_files = sorted(glob.glob(os.path.join(active_dir, "turn_*.md")), key=get_turn_number)
    if len(active_files) >= MAX_ACTIVE_TURNS:
        # Prune down to ACTIVE_BASELINE_TURNS in a batch (oldest first)
        num_to_archive = len(active_files) - ACTIVE_BASELINE_TURNS
        turns_to_archive = active_files[:num_to_archive]
        for fpath in turns_to_archive:
            dest = os.path.join(archive_dir, os.path.basename(fpath))
            shutil.move(fpath, dest)

    return turn_file

def load_active_turns(campaign_dir: str) -> list[dict]:
    active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
    active_files = sorted(glob.glob(os.path.join(active_dir, "turn_*.md")), key=get_turn_number)
    
    turns = []
    for fpath in active_files:
        with open(fpath, "r", encoding="utf-8") as f:
            turns.append({
                "file": os.path.basename(fpath),
                "turn": get_turn_number(fpath),
                "content": f.read()
            })
    return turns
