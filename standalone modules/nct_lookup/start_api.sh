#!/bin/bash

echo "=== NCT Lookup API Setup ==="

# Create results directory
mkdir -p results

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check .env file exists
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# SERP API Key (for Google Search & Scholar)
SERPAPI_KEY=c4c32ac751923eafd8d867eeb14c433e245aebfdbc0261cb2a8357e08ca34ff0

# NCBI API Key (optional - improves rate limits)
NCBI_API_KEY=ca84a2b20dc7059e4d06c9fd4ee52678c508
EOF
fi

# Start API
echo ""
echo "Starting NCT Lookup API on port 8000..."
echo "API Documentation: http://localhost:8000/docs"
echo ""
uvicorn nct_api:app --reload --port 8000