#!/bin/sh
set -e

cleanup() {
    echo "Stopping all services..."
    if [ -n "$UI_PID" ]; then
        kill "$UI_PID" 2>/dev/null || true
    fi
    if [ -n "$ENGINE_PID" ]; then
        kill "$ENGINE_PID" 2>/dev/null || true
    fi
    exit 0
}

TARGET="${1:-all}"

case "$TARGET" in
    engine)
        exec python ENGINE/engine.py
        ;;
    ui)
        exec python -m http.server 3000 --directory UI
        ;;
    all)
        trap cleanup INT TERM

        echo "Starting UI on port 3000..."
        python -m http.server 3000 --directory UI &
        UI_PID=$!

        echo "Starting Engine API on port 8000..."
        python ENGINE/engine.py &
        ENGINE_PID=$!

        wait "$ENGINE_PID"
        cleanup
        ;;
    *)
        exec "$@"
        ;;
esac
