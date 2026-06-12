from .base import *

DEBUG = config("DEBUG", default=False, cast=bool)

SECRET_KEY = config("SECRET_KEY", default="insecure-deploy-key-change-me")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)

_ssl_header = config("SECURE_PROXY_SSL_HEADER", default=None)
if _ssl_header and isinstance(_ssl_header, str) and "," in _ssl_header:
    _ssl_header = tuple(_ssl_header.split(","))
SECURE_PROXY_SSL_HEADER = _ssl_header

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
