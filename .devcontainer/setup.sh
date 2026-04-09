#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install poetry==1.7.1

echo "==> Installing project dependencies..."
poetry install --no-root

echo "==> Installing pre-commit hooks..."
pre-commit install

echo "==> Setting up AWS CLI config skeleton..."
mkdir -p ~/.aws
cat > ~/.aws/config << 'EOF'
[default]
region = ap-south-1
output = json
EOF

echo "==> Setup complete!"