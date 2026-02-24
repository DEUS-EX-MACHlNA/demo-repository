#!/bin/bash

echo "🛑 Stopping existing production containers..."
docker-compose -f docker-compose.prod.yml down

echo "🚀 Starting production environment..."
docker-compose -f docker-compose.prod.yml up -d --build

echo "✅ Production server started!"
echo "👉 To view logs, run: docker-compose -f docker-compose.prod.yml logs -f"