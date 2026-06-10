# Ftree

Family tree application built with Django.

## Setup

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

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```
