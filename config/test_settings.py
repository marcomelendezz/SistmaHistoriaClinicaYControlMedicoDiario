"""Isolated tests: never open the repository database or contact SMTP."""
import os

os.environ.setdefault('DJANGO_SECRET_KEY', 'synthetic-tests-only-5948af1c69e64fe98ed27aae07e92c84-DO-NOT-DEPLOY')
from .settings import *  # noqa: E402,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:', 'TEST': {'NAME': ':memory:'}}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
DEFAULT_FROM_EMAIL = 'noreply@example.invalid'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
