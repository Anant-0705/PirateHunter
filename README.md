# PirateHunt

Real-time live-stream piracy detection system for sports broadcasts. Phase 1 focuses on fingerprinting core and project scaffold.

## Quick Start

### Prerequisites

- Python 3.11+
- `ffmpeg` (system dependency)
- `chromaprint` (system dependency)
- `uv` package manager (or pip)

**macOS:**
```bash
brew install ffmpeg chromaprint
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg chromaprint
```

**Windows:**
- Download FFmpeg from https://ffmpeg.org/download.html
- Download Chromaprint tools from https://acoustid.org/chromaprint

### Installation

1. Clone the repository:
```bash
cd PirateHunter
```

2. Install dependencies with `uv`:
```bash
uv sync
```

Or with pip:
```bash
pip install -e ".[dev]"
```

3. Set up environment:
```bash
cp .env.example .env
```

4. Start services (PostgreSQL + Redis):
```bash
docker-compose up -d
```

### Running Tests

Add a sample video file to `tests/fixtures/sample.mp4` to run integration tests. Tests will skip gracefully if missing.

```bash
pytest -v
```

### Running the API

```bash
uvicorn piratehunt.api.app:app --reload
```

Server runs on `http://localhost:8000`. Check `/health` endpoint:
```bash
curl http://localhost:8000/health
```

### Running the Real-Time Dashboard (Phase 6)

#### Backend Setup
The API server includes WebSocket support for real-time event streaming. Ensure Redis and PostgreSQL are running:
```bash
docker-compose up -d
```

#### Frontend Setup
```bash
cd dashboard
npm install
npm run dev
```

Dashboard runs on `http://localhost:3000`

Create `.env.local` in the `dashboard/` directory:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_USE_MOCK=false
```

#### Full System Integration
**Terminal 1 - Backend API:**
```bash
python -m piratehunt.api.main --host localhost --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd dashboard
npm run dev
```

**Terminal 3 - Demo (Workers):**
```bash
python -m piratehunt.cli worker dmca  # DMCA processor
```

Visit `http://localhost:3000` to see live pirate detection and takedown tracking.

### Dashboard Features

- **Real-Time 3D Globe**: Animated pins showing pirate streams by location
- **Event Feed**: Live ticker of detections, verifications, and takedowns
- **Takedown Funnel**: Visual pipeline of detected → verified → drafted → submitted → taken down
- **Revenue Tracker**: Estimated financial impact of piracy
- **Connection Status**: Real-time WebSocket connectivity indicator

## Project Structure

```
piratehunt/
├── src/piratehunt/
│   ├── config.py               # Pydantic settings
│   ├── fingerprint/            # Fingerprinting core
│   │   ├── audio.py            # Chromaprint wrapper
│   │   ├── visual.py           # pHash + dHash
│   │   ├── extractor.py        # ffmpeg wrapper
│   │   └── types.py            # Pydantic models
│   ├── index/                  # Vector indexing
│   │   ├── faiss_store.py      # Visual hash index
│   │   └── audio_store.py      # Audio fingerprint store
│   ├── api/
│   │   ├── app.py              # FastAPI application
│   │   ├── routers/            # API endpoints
│   │   │   ├── health.py
│   │   │   ├── matches.py
│   │   │   ├── discovery.py
│   │   │   ├── verification.py
│   │   │   ├── takedowns.py
│   │   │   ├── rights_holders.py
│   │   │   └── dashboard.py    # Aggregation endpoints (Phase 6)
│   │   └── realtime/           # WebSocket bridge (Phase 6)
│   │       ├── types.py        # Event types
│   │       ├── bridge.py       # Redis → WebSocket
│   │       ├── manager.py      # Connection management
│   │       ├── geolocation.py  # URL → location lookup
│   │       └── endpoint.py     # WebSocket endpoint
│   ├── dmca/                   # DMCA notice generation (Phase 5)
│   ├── db/                     # Database models
│   └── cli.py                  # Command-line interface
├── dashboard/                  # Next.js frontend (Phase 6)
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx            # Main dashboard
│   │   └── globals.css
│   ├── components/             # React components
│   ├── lib/                    # Utilities
│   │   ├── store.ts            # Zustand state
│   │   ├── ws.ts               # WebSocket client
│   │   ├── api.ts              # Fetch wrappers
│   │   └── types.ts            # TypeScript types
│   ├── styles/
│   ├── package.json
│   └── tsconfig.json
├── tests/                      # Pytest suite
├── docker-compose.yml          # Services
├── pyproject.toml              # Project config
├── PHASE6_BUILD.md             # Phase 6 build summary
└── README.md
```

## Project Phases

### Phase 1 ✅
- ✅ Project scaffold and dependencies
- ✅ Audio fingerprinting with Chromaprint
- ✅ Visual fingerprinting (pHash + dHash)
- ✅ Media extraction (ffmpeg integration)
- ✅ In-memory fingerprint indices
- ✅ Health check endpoint

### Phase 2-5 ✅
- ✅ Database persistence (PostgreSQL + SQLAlchemy)
- ✅ Ingestion endpoints and candidate streams
- ✅ Streaming verification pipelines
- ✅ Detection agents with audio/visual scoring
- ✅ DMCA notice generation and takedown tracking
- ✅ Rights holder management

### Phase 6 ✅ (JUST COMPLETED)
- ✅ WebSocket real-time event bridge (Redis → clients)
- ✅ Dashboard aggregation endpoints (summary, timeline, pirates, funnel)
- ✅ Next.js 14 frontend with dark theme
- ✅ Live event feed, 3D globe visualization, takedown funnel
- ✅ Zustand state management + auto-reconnecting WebSocket client
- ✅ Revenue loss estimation + real-time metrics

### Planned for Future Phases

- Mock event generator for offline demos
- Full deck.gl 3D globe with animated pins (currently placeholder)
- Frontend unit tests (Vitest + React Testing Library)
- Screenshot automation for demo documentation
- Platform-specific crawlers (YouTube, Telegram, Discord, etc.)
- Automated DMCA submission to hosting providers

## Development

### Code Style

Code is formatted with Black and checked with Ruff. Format and lint:

```bash
black src tests
ruff check --fix src tests
```

### Type Hints

All code uses full type hints with `from __future__ import annotations`.

## License

MIT
