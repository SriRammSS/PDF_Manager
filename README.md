# PDF Manager

Full-stack PDF Manager application running entirely locally (no Docker).

## Prerequisites

- PostgreSQL running on localhost:5433
- Redis running on localhost:6379
- Python 3.12+
- Node.js 18+

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Celery (optional, for async tasks)

```bash
# Use the start script (fixes macOS fork + pikepdf crash)
./start-celery.sh

# Or manually:
cd backend && source .venv/bin/activate
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES  # macOS fix
celery -A app.tasks worker --loglevel=info --pool=solo
```

## Database

- Host: localhost
- Port: 5433
- Database: pdf_management_app
- User: postgres

## API

- Backend: http://localhost:8000
- Health: GET /api/health
- Frontend: http://localhost:5173
