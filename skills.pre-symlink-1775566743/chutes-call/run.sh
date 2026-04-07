#!/usr/bin/env bash
# chutes-call: Docker lifecycle for the centralized Chutes.ai LLM gateway.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="embry-chutes-call"
IMAGE_NAME="chutes-call:latest"
PORT="${CHUTES_CALL_PORT:-8630}"

cmd_build() {
    echo "Building ${IMAGE_NAME}..."
    if [[ -f "${SKILL_DIR}/docker-compose.yml" ]]; then
        docker compose -f "${SKILL_DIR}/docker-compose.yml" build
    else
        docker build -t "${IMAGE_NAME}" "${SKILL_DIR}"
    fi
}

cmd_start() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container ${CONTAINER_NAME} already running on port ${PORT}"
        echo "Use './run.sh stop' first or './run.sh health' to check status"
        return 1
    fi

    # Remove stopped container if exists
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

    # Build if image doesn't exist
    if ! docker image inspect "${IMAGE_NAME}" &>/dev/null; then
        cmd_build
    fi

    # Collect env vars for API keys
    local env_args=()
    for var in CHUTES_API_KEY CHUTES_API_TOKEN OPENROUTER_API_KEY GEMINI_API_KEY CHUTES_CALL_PORT; do
        if [ -n "${!var:-}" ]; then
            env_args+=(-e "${var}=${!var}")
        fi
    done

    echo "Starting ${CONTAINER_NAME} on port ${PORT}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --network host \
        --restart unless-stopped \
        --label "embry.skill=chutes-call" \
        --label "embry.port=${PORT}" \
        "${env_args[@]}" \
        "${IMAGE_NAME}"

    # Wait for health
    local retries=0
    while [ $retries -lt 10 ]; do
        if curl -sf "http://localhost:${PORT}/health" &>/dev/null; then
            echo "Gateway healthy on port ${PORT}"
            return 0
        fi
        sleep 1
        retries=$((retries + 1))
    done
    echo "WARNING: Gateway started but health check not responding after 10s"
}

cmd_stop() {
    echo "Stopping ${CONTAINER_NAME}..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null && echo "Stopped" || echo "No container to stop"
}

cmd_status() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "RUNNING"
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    else
        echo "STOPPED"
    fi
}

cmd_health() {
    curl -sf "http://localhost:${PORT}/health" | python3 -m json.tool 2>/dev/null || echo "Gateway not responding on port ${PORT}"
}

cmd_logs() {
    docker logs -f "${CONTAINER_NAME}" 2>/dev/null || echo "No container found"
}

cmd_test() {
    echo "=== chutes-call smoke test ==="
    cmd_start
    echo ""
    echo "--- Health ---"
    cmd_health
    echo ""
    echo "--- Usage ---"
    curl -sf "http://localhost:${PORT}/usage" | python3 -m json.tool 2>/dev/null
    echo ""
    echo "--- Queue ---"
    curl -sf "http://localhost:${PORT}/queue" | python3 -m json.tool 2>/dev/null
    echo ""
    cmd_stop
    echo "=== smoke test complete ==="
}

cmd_usage() {
    curl -sf "http://localhost:${PORT}/usage" | python3 -m json.tool 2>/dev/null || echo "Gateway not responding"
}

cmd_queue() {
    curl -sf "http://localhost:${PORT}/queue" | python3 -m json.tool 2>/dev/null || echo "Gateway not responding"
}

case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    health)  cmd_health ;;
    logs)    cmd_logs ;;
    build)   cmd_build ;;
    test)    cmd_test ;;
    usage)   cmd_usage ;;
    queue)   cmd_queue ;;
    *)
        echo "Usage: $0 {start|stop|status|health|logs|build|test|usage|queue}"
        echo ""
        echo "  start   - Build (if needed) and start the gateway container"
        echo "  stop    - Stop and remove the container"
        echo "  status  - Show container status"
        echo "  health  - Query /health endpoint"
        echo "  logs    - Tail container logs"
        echo "  build   - Build the Docker image"
        echo "  test    - Start, smoke test, stop"
        echo "  usage   - Show accumulated cost/token stats"
        echo "  queue   - Show live queue dashboard"
        ;;
esac
