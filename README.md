# Ftree

Family tree application built with Django.

## Local Setup

```bash
# Clone the repository
git clone <repo-url>
cd ftree

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your settings:
#   SECRET_KEY=your-secret-key
#   DEBUG=True
#   DATABASE_URL=postgres://user:pass@localhost:5432/ftree  (optional, defaults to SQLite)

# Run migrations
python manage.py migrate

# Seed demo data
python manage.py seed_demo_family

# Start the development server
python manage.py runserver
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | insecure-dev-key | Django secret key |
| `DEBUG` | False | Debug mode (set True locally) |
| `ALLOWED_HOSTS` | 127.0.0.1,localhost | Comma-separated hosts |
| `DATABASE_URL` | (SQLite) | Database URL (e.g. postgres://...) |
| `TIME_ZONE` | UTC | Time zone |

## Settings

- **Local**: `config.settings.local` (default for manage.py)
- **Production**: `config.settings.production` (set `DJANGO_SETTINGS_MODULE` accordingly)

## Commands

```bash
# Run development server
python manage.py runserver

# Seed demo family data
python manage.py seed_demo_family

# Run tests
python manage.py test

# Create migrations
python manage.py makemigrations
```
