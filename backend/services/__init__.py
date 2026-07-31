"""
PulseOS Services Package
========================
Orchestration layer sitting between the HTTP route handlers and the domain
engine classes (core/, ai/, optimization/, metrics/).

Service classes:
  GeminiService       -- sole gateway to the Google Gemini generative API
  NetworkService      -- topology generation, digital twin synchronisation
  PredictionService   -- congestion load forecasting
  OptimizationService -- QUBO formulation and QuantumSON solver execution
  ScenarioService     -- scenario simulation
  DashboardService    -- cross-subsystem KPI aggregation

Dependency injection:
  services/deps.py provides FastAPI Depends() providers for all services.
  Always inject services via Depends() in route handlers — never instantiate
  them directly inside a route function.

AI integration contract:
  GeminiService is the ONLY module that may import google.generativeai.
  All current and future AI features (Copilot, Recommendation Engine,
  Executive Summary, Explainable AI) MUST call GeminiService — never the
  Gemini SDK directly.
"""
