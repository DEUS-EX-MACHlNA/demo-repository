#!/bin/bash

export COMPOSE_HTTP_TIMEOUT=300
export DOCKER_CLIENT_TIMEOUT=300

echo "🔧 Activating 'deus' conda environment..."
source /home/ubuntu/anaconda3/etc/profile.d/conda.sh
conda activate deus

echo "🛑 Stopping existing production containers..."
docker-compose --env-file .env.prod -f docker-compose.prod.yml down

echo "🚀 Starting production environment..."
docker-compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

echo "✅ Production server started!"
echo "👉 To view logs, run: docker-compose --env-file .env.prod -f docker-compose.prod.yml logs -f"