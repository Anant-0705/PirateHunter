# 🏴‍☠️ PirateHunt

**Real-time live-stream piracy detection system for sports broadcasts.**

PirateHunt monitors live sports streams across platforms, uses audio/visual fingerprinting + AI verification to detect unauthorized restreams, and auto-generates DMCA takedown notices — all in real-time.

---

## 📋 Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.10+ | Backend API & workers |
| **Node.js** | 18+ | Dashboard frontend |
| **Docker Desktop** | Latest | PostgreSQL + Redis |
| **FFmpeg** | Latest | *(optional)* Video processing |

---

## 🚀 Quick Start

### 1. Clone & Configure

**Git Bash:**
```bash
cp .env.example .env
```

### 2. Start Database Services

```bash
docker compose up -d
```

### 3. Setup Backend (Python)

Create and activate your virtual environment, then install dependencies.

**Git Bash:**
```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate venv
source venv/Scripts/activate

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -e .[dev]
```

### 4. Initialize Database

**Git Bash:**
```bash
python scripts/create_tables.py
```

### 5. Setup Dashboard (Frontend)

```bash
cd dashboard
npm install
cd ..
```

---

## ▶️ Running the System

You need **3 terminals** for the full system:

### Terminal 1 — Backend API

```bash
.\venv\Scripts\Activate.ps1
python -m piratehunt.api.main --host localhost --port 8000
```

| Endpoint | URL |
|----------|-----|
| API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

### Terminal 2 — Dashboard Frontend

```bash
cd dashboard
npm run dev
```

Dashboard: http://localhost:3000

### Terminal 3 — Workers *(optional)*

```bash
.\venv\Scripts\Activate.ps1
python -m piratehunt.cli worker dmca
```

---

## 📁 Project Structure

```
PirateHunter/
├── src/piratehunt/              # Python backend
│   ├── api/                     # FastAPI app + routers
│   │   ├── app.py               # FastAPI application
│   │   ├── routers/             # REST endpoints
│   │   │   ├── health.py
│   │   │   ├── matches.py
│   │   │   ├── discovery.py
│   │   │   ├── verification.py
│   │   │   ├── takedowns.py
│   │   │   ├── rights_holders.py
│   │   │   └── dashboard.py     # Aggregation endpoints
│   │   └── realtime/            # WebSocket bridge (Redis → clients)
│   ├── fingerprint/             # Audio (Chromaprint) + Visual (pHash/dHash)
│   ├── index/                   # FAISS vector store + audio store
│   ├── agents/                  # Detection agent orchestration
│   ├── ingestion/               # Stream ingestion pipeline
│   ├── verification/            # AI verification + evidence collection
│   ├── dmca/                    # DMCA notice generation + tracking
│   ├── db/                      # SQLAlchemy models + repository
│   ├── config.py                # Pydantic settings
│   └── cli.py                   # CLI entry point
│
├── dashboard/                   # Next.js 14 frontend
│   ├── app/                     # App Router (layout, page)
│   ├── components/              # React components
│   ├── lib/                     # Zustand store, WebSocket, API client
│   └── styles/                  # Tailwind CSS
│
├── tests/                       # Pytest test suite
├── scripts/                     # Utility scripts
│   ├── demo.py                  # End-to-end demo
│   ├── simulate_dashboard.py    # Push mock events to dashboard
│   └── create_tables.py         # Direct table creation (no Alembic)
│
├── alembic/                     # Database migrations
├── docker-compose.yml           # PostgreSQL + Redis
├── pyproject.toml               # Python project config
├── requirements.txt             # Python dependencies
├── setup_venv.ps1               # Backend setup (PowerShell)
├── .env.example                 # Environment template
└── .gitignore
```

---

## 🧪 Development

### Run Tests

```bash
pytest -v
```

### Code Style

```bash
black src tests
ruff check --fix src tests
```

### Run Demo (offline)

```bash
python scripts/demo.py
```

---

## 🏗️ Architecture

```
                    ┌─────────────┐
                    │  Dashboard  │ (Next.js)
                    │  :3000      │
                    └──────┬──────┘
                           │ WebSocket + REST
                    ┌──────┴──────┐
                    │  FastAPI    │
                    │  :8000      │
                    └──┬───┬───┬──┘
                       │   │   │
              ┌────────┘   │   └────────┐
              │            │            │
        ┌─────┴─────┐ ┌───┴────┐ ┌─────┴──────┐
        │ PostgreSQL │ │ Redis  │ │ Gemini API │
        │ + pgvector │ │        │ │ (optional) │
        └────────────┘ └────────┘ └────────────┘
```

**Pipeline:** Discover → Ingest → Fingerprint → Verify (AI) → DMCA → Takedown

---

## 📄 License

MIT
