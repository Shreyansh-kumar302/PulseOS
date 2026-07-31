# PulseOS

PulseOS is a next-generation telecom network management system featuring a digital twin, real-time prediction capabilities, AI-driven automation copilot, and quantum/classical optimization solvers (QPIAI).

## Project Structure

```
PulseOS/
│
├── frontend/             # Vite + React Control Panel Frontend
│   ├── public/
│   ├── src/
│   │   ├── pages/        # Dashboard, network viewer, optimize screens
│   │   ├── components/   # Reusable UI controls, maps, graphs
│   │   ├── api/          # Axios/fetch hooks for backend communications
│   │   ├── assets/       # Media, icons, logos
│   │   ├── App.jsx       # Main App Component
│   │   └── main.jsx      # Entrypoint
│   └── package.json
│
├── backend/              # FastAPI Backend API
│   ├── app.py            # Main App Entrypoint (uvicorn entry)
│   ├── config.py         # Config variables (env-var overridable)
│   │
│   ├── routes/           # FastAPI routers — one file per domain
│   │   ├── network.py
│   │   ├── scenario.py
│   │   ├── prediction.py
│   │   ├── optimize.py
│   │   ├── dashboard.py
│   │   └── metrics.py
│   │
│   ├── core/             # Base telecom simulation logics
│   │   ├── network_generator.py
│   │   ├── digital_twin.py
│   │   └── feature_engineering.py
│   │
│   ├── ai/               # AI & LLM Copilot engines
│   │   ├── prediction_engine.py
│   │   ├── decision_engine.py
│   │   ├── copilot.py
│   │   └── summary.py
│   │
│   ├── optimization/     # Quantum/Classical Optimization Solver engines
│   │   ├── qubo.py
│   │   └── qpiai.py
│   │
│   ├── metrics/          # SLA and performance counters
│   │   └── metrics_engine.py
│   │
│   ├── data/             # Mock DB JSON data stores
│   │   ├── network.json
│   │   ├── prediction.json
│   │   └── optimization.json
│   │
│   └── database/         # DB interfaces
│       └── db.py
│
├── dataset/              # CSV Datasets for training and analysis
│   ├── towers.csv
│   ├── users.csv
│   └── events.csv
│
├── docs/                 # Documentation and Diagrams
│   ├── architecture.png
│   ├── workflow.png
│   └── report.pdf
│
├── README.md
├── requirements.txt
└── .gitignore
```

## Getting Started

### Backend
1. Create a virtual environment and install dependencies:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r ../requirements.txt
   ```
2. Run the application:
   ```bash
   uvicorn app:app --reload --port 8000
   ```

### Frontend
1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```
2. Start the Vite dev server:
   ```bash
   npm run dev
   ```
