# File: MyDentalPortal/extensions.py
# Single source of truth for Flask extensions.
# All blueprints import mongo from here — never from app.py or app_factory.py.

from flask_pymongo import PyMongo
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

mongo = PyMongo()

# Rate limiter. Memory storage is fine for a single instance / dev; for a
# multi-worker production deploy, point storage_uri at a shared store (Redis).
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=[],
)
