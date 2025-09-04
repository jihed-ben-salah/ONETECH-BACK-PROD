"""Entry point for Vercel serverless using Django's WSGI application.

Vercel Python builder looks for a file exposing a WSGI/ASGI callable named `app`.
We import Django's WSGI application and expose it as `app`.
"""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

from core.wsgi import application  # noqa

app = application  # Vercel expects `app`


def handler(environ, start_response):  # optional explicit handler
    return app(environ, start_response)
