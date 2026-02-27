export DB_HOST=localhost && \
export DB_PORT=5434 && \
export DB_NAME=maratang_db && \
export DB_USER=maratang_admin && \
export DB_PASSWORD=password && \
export REDIS_URL=redis://localhost:6380/0 && \
/home/ubuntu/anaconda3/envs/deus/bin/python benchmark_redis.py