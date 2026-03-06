<div align="center">

# 📄 PDF Manager

### Full-Stack PDF Management Platform with Visual Canvas Editor

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Async-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-Redis_Queue-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

<br/>

> Upload, view, annotate, and version-track PDF files through a browser-based canvas editor — with async Celery processing, HTTP range streaming, JWT authentication, and a full audit log.

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)

---

## Overview

PDF Manager is a production-style document management system where every interaction — upload, view, edit, delete — is tracked, queued, streamed, and versioned. The canvas editor is built on Fabric.js over a PDF.js renderer, giving users freehand drawing, text annotation, highlights, whiteout, and shape tools directly in the browser.

| Dimension | Value |
|-----------|-------|
| Auth | JWT HS256 (register/login/refresh) |
| Background tasks | Celery 5 + Redis (page extraction, edit processing, purge) |
| PDF engine | pikepdf (write/edit) + pdfminer.six (text extraction) |
| Rate limiting | 10 uploads/minute per user (slowapi) |
| Audit logging | Every API event written to `logs` table |
| Soft delete | Marked `deleted_at`; Celery beat purges files after 30 days |

---

## Features

### Document Management
- Multi-file upload with async Celery processing (page count extraction, status tracking)
- HTTP **Range header streaming** — efficient partial PDF delivery for large files
- **Version history** — every save creates a new immutable version; all prior versions are stored and streamable
- **Soft delete + 30-day purge** — Celery beat task physically removes files and DB records after the grace period

### Visual Canvas Editor
Built on **Fabric.js v7** over a **PDF.js** page renderer:

| Tool | Description |
|------|-------------|
| Freehand text | Place text annotations anywhere on the page |
| Text editing | Edit existing PDF text content in-place |
| Highlight | Colored overlay highlight tool |
| Whiteout / Erase | Redact content with white rectangles |
| Shapes | Rectangle and line drawing tools |
| Freehand draw | Free-form pen tool |

### Page Management
- Drag-and-drop page reorder (`@dnd-kit/core + @dnd-kit/sortable`)
- Per-page rotation
- Page deletion

### Security & Observability
- JWT authentication with refresh token support
- Per-user request-ID middleware for distributed tracing
- Rate limiting on upload endpoints
- Full audit log queryable via API (`/api/logs`)

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              Browser (React 19 + TypeScript + Vite 7)            │
│                                                                    │
│  PDF.js renderer  ←→  Fabric.js canvas editor                    │
│  @dnd-kit drag-drop  ·  TanStack Query  ·  Tailwind CSS v4       │
└────────────────────┬────────────────────────────────────────────┘
                     │  /api/* + Range streaming
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI (Uvicorn, async)                      │
│                                                                    │
│  Routers: auth · pdfs · users · logs                             │
│  Middleware: request-ID injection · slowapi rate limiter         │
│  Services: pdf_service · edit_service · storage_service          │
└────────┬──────────────────────────┬─────────────────────────────┘
         │  asyncpg (SQLAlchemy)     │  Celery tasks
         ▼                           ▼
┌──────────────┐           ┌────────────────────────┐
│ PostgreSQL   │           │  Redis + Celery Worker  │
│ 4 tables     │           │                         │
│ users        │           │  process_uploaded_pdf   │
│ pdfs         │           │  save_edited_pdf        │
│ pdf_versions │           │  purge_deleted_pdfs     │
│ logs         │           │  (Celery Beat, 30-day)  │
└──────────────┘           └────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│  Local file storage         │
│  storage/<user_id>/<pdf_id> │
│  (original + versions)      │
└────────────────────────────┘
```

---

## Tech Stack

### Backend

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI + Uvicorn (async) |
| ORM | SQLAlchemy 2.x async + Alembic |
| Database | PostgreSQL (port 5433) |
| Async driver | asyncpg |
| Task queue | Celery 5 + Redis |
| PDF engine | pikepdf (edit/write) · pdfminer.six (extraction) |
| Auth | python-jose (JWT) + bcrypt |
| Rate limiting | slowapi |
| Config | pydantic-settings |

### Frontend

| Component | Technology |
|-----------|-----------|
| Framework | React 19 + TypeScript + Vite 7 |
| Canvas editor | Fabric.js v7 |
| PDF rendering | pdfjs-dist v3 + @react-pdf-viewer |
| Drag & drop | @dnd-kit/core + @dnd-kit/sortable |
| Styling | Tailwind CSS v4 |
| HTTP client | Axios |
| Notifications | react-hot-toast |
| Routing | react-router-dom v7 |
| Icons | lucide-react |

---

## Database Schema

```
users ──────────────────── pdfs ─── pdf_versions
                             │
                           logs (audit trail for every API event)
```

| Table | Key Columns |
|-------|-------------|
| `users` | `id` (UUID), `email`, `password_hash`, `created_at` |
| `pdfs` | `id`, `user_id`, `filename`, `file_path`, `page_count`, `status`, `deleted_at` |
| `pdf_versions` | `id`, `pdf_id`, `version_number`, `file_path`, `created_at` |
| `logs` | `id`, `user_id`, `action`, `resource_id`, `request_id`, `timestamp` |

---

## API Reference

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| `POST` | `/api/auth/register` | Public | Create user account |
| `POST` | `/api/auth/login` | Public | Authenticate, return JWT |
| `POST` | `/api/auth/refresh` | JWT | Refresh access token |
| `POST` | `/api/pdfs/upload` | JWT | Upload PDF (rate-limited: 10/min) |
| `GET` | `/api/pdfs` | JWT | List user's PDFs with status |
| `GET` | `/api/pdfs/:id/stream` | JWT | HTTP Range streaming |
| `POST` | `/api/pdfs/:id/edit` | JWT | Submit canvas operations (async via Celery) |
| `GET` | `/api/pdfs/:id/versions` | JWT | List version history |
| `DELETE` | `/api/pdfs/:id` | JWT | Soft delete (30-day purge scheduled) |
| `GET` | `/api/users/me` | JWT | Get current user profile |
| `GET` | `/api/logs` | JWT | Query audit log |

---

## Getting Started

### Prerequisites
- Python 3.12+, Node.js 20+, PostgreSQL 15+, Redis

### 1. Backend Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:
```ini
DATABASE_URL=postgresql+asyncpg://postgres:<password>@localhost:5433/pdf_management_app
REDIS_URL=redis://localhost:6379
JWT_SECRET=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
STORAGE_PATH=./storage
```

```bash
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### 2. Start Celery Worker

```bash
bash start-celery.sh
```

### 3. Frontend Setup

```bash
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

---

## Project Structure

```
pdf-manager/
├── backend/
│   ├── main.py                      # FastAPI entry point
│   ├── app/
│   │   ├── api/                     # auth · pdfs · users · logs routers
│   │   ├── core/                    # config · deps · security · middleware · limiter
│   │   ├── db/                      # models · session · sync_session
│   │   ├── services/                # pdf_service · edit_service · storage_service
│   │   └── tasks/                   # celery_app · pdf_tasks (process, save, purge)
│   └── tests/e2e/                   # 8 test modules (auth → upload → edit → logs)
├── frontend/
│   └── src/
│       ├── pages/                   # Login · Signup · Dashboard · Viewer · Editor · Logs
│       └── components/              # ToolbarSidebar · PropertiesPanel · PageManagerPanel
├── start-backend.sh
└── start-celery.sh
```
