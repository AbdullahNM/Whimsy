#!/usr/bin/env bash
# ==============================================================================
# Whimsy CYOA Engine — Comprehensive Test Suite Runner
# ==============================================================================
# Executes Python unit/integration tests and Node.js UI/engine test suites.
# Returns exit code 0 if all tests pass, non-zero otherwise.
# ==============================================================================

set -e

# Terminal colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD}${CYAN}            Whimsy CYOA Engine — Automated Test Suite Runner                  ${NC}"
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "Working Directory: ${ROOT_DIR}\n"

# ------------------------------------------------------------------------------
# 1. Python Engine Test Suite (unittest)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${YELLOW}=== [1/2] Running Python Engine Tests (unittest) ===${NC}"
python3 -m unittest discover -s tests -p "test_*.py" -v

echo -e "\n${GREEN}✔ Python Engine Test Suite: PASSED${NC}\n"

# ------------------------------------------------------------------------------
# 2. JavaScript / UI Engine Test Suite (Node.js)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${YELLOW}=== [2/2] Running JavaScript & UI Engine Tests (node --test) ===${NC}"
node --test tests/test_markdown_parser.js tests/test_metrics_extractor.js

echo -e "\n${GREEN}✔ JavaScript & UI Engine Test Suite: PASSED${NC}\n"

# ------------------------------------------------------------------------------
# 3. OpenSpec Specification Validation
# ------------------------------------------------------------------------------
echo -e "${BOLD}${YELLOW}=== [3/3] Validating OpenSpec Specifications ===${NC}"
if command -v openspec &> /dev/null; then
    openspec validate --all
    echo -e "\n${GREEN}✔ OpenSpec Validation: PASSED${NC}\n"
else
    echo -e "${YELLOW}Notice: openspec CLI not found in PATH, skipping OpenSpec validation.${NC}\n"
fi

echo -e "${BOLD}${GREEN}==============================================================================${NC}"
echo -e "${BOLD}${GREEN}         ALL WHIMSY ENGINE & UI TEST SUITES PASSED SUCCESSFULLY (0 ERRORS)    ${NC}"
echo -e "${BOLD}${GREEN}==============================================================================${NC}"
