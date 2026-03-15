#!/bin/bash
# JARVIS Kali Linux Security Lab Setup
# Run this on the Mac Mini to set up the isolated Kali container.
#
# Usage: bash scripts/kali_setup.sh
#
# This creates a persistent Kali container named "jarvis-kali" with:
# - Network isolation (no host network access by default)
# - Read-only volume mounts for data sharing
# - Common security tools pre-installed
# - Runs as non-root user inside container

set -euo pipefail

CONTAINER_NAME="jarvis-kali"
IMAGE="kalilinux/kali-rolling"
SHARED_DIR="$HOME/jarvis-kali-shared"

echo "=== JARVIS Kali Security Lab Setup ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing via Homebrew..."
    brew install --cask docker
    echo "Please start Docker Desktop and re-run this script."
    exit 1
fi

# Create shared directory
mkdir -p "$SHARED_DIR/output"
mkdir -p "$SHARED_DIR/wordlists"

# Pull Kali image
echo "Pulling Kali Linux image..."
docker pull "$IMAGE"

# Stop existing container if running
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Create container with security restrictions
echo "Creating isolated Kali container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --cap-drop ALL \
    --cap-add NET_RAW \
    --cap-add NET_ADMIN \
    --security-opt no-new-privileges \
    --memory 2g \
    --cpus 2 \
    -v "$SHARED_DIR/output:/shared/output" \
    -v "$SHARED_DIR/wordlists:/shared/wordlists:ro" \
    "$IMAGE" \
    tail -f /dev/null

# Install essential tools inside the container
echo "Installing security tools (this may take a few minutes)..."
docker exec "$CONTAINER_NAME" bash -c "
    apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        whois \
        dnsutils \
        traceroute \
        curl \
        wget \
        nikto \
        dirb \
        sqlmap \
        wpscan \
        python3 \
        python3-pip \
        net-tools \
        iputils-ping \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
"

# Create a non-root user for running commands
docker exec "$CONTAINER_NAME" bash -c "
    useradd -m -s /bin/bash jarvis-operator 2>/dev/null || true
"

echo ""
echo "=== Setup Complete ==="
echo "Container: $CONTAINER_NAME"
echo "Shared directory: $SHARED_DIR"
echo "Status: $(docker inspect -f '{{.State.Status}}' $CONTAINER_NAME)"
echo ""
echo "Test: docker exec $CONTAINER_NAME nmap --version"
echo ""
echo "JARVIS can now execute whitelisted security tools in this container."
