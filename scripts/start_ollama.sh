#!/bin/bash
# Start Ollama service for RealTypeCoach text generation
# Uses gemma2:2b model (fits in 8GB VRAM)

set -e

MODEL="gemma2:2b"

echo "Starting Ollama service for RealTypeCoach..."
echo "Model: $MODEL"

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start Ollama service (if not running)
if ! systemctl is-active --quiet ollama; then
    echo "Starting Ollama service..."
    sudo systemctl start ollama
    echo "Waiting for Ollama to start..."
    sleep 5
fi

# Check if service is running
if ! systemctl is-active --quiet ollama; then
    echo "❌ Failed to start Ollama service"
    exit 1
fi

# Pull model if not available
if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling $MODEL model..."
    ollama pull "$MODEL"
fi

echo ""
echo "✓ Ollama is running!"
echo "  Model: $MODEL"
echo "  API: http://localhost:11434"
echo ""
echo "Commands:"
echo "  ollama list          - List available models"
echo "  ollama ps            - Show running models"
echo "  sudo systemctl stop ollama  - Stop service"
