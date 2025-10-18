# backend/api/index.py
from vercel_wsgi import handle
from app import app as flask_app  # your Flask instance in backend/app.py

def handler(event, context):
    return handle(flask_app, event, context)
