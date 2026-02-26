import os
from dotenv import load_dotenv
print("Before load_dotenv:", os.getenv("REDIS_URL"))
load_dotenv()
print("After load_dotenv:", os.getenv("REDIS_URL"))
