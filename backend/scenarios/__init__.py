"""
PulseOS Scenarios Package
=========================
The Scenario Engine — first real business-logic component.

Public interface:
    from scenarios.scenario_engine import ScenarioEngine

    engine = ScenarioEngine()
    scenario = engine.run(request, network_state)

Internal structure:
    scenario_engine.py   ← ScenarioEngine class (entry point)
    handlers.py          ← Pure handler functions (one per ScenarioEventType)
    effects.py           ← ScenarioEffect dataclass + SCENARIO_DEFAULTS

The scenarios/ package imports only from schemas/.
Nothing from services/ or routes/ may import directly from handlers.py or
effects.py — all access must go through ScenarioEngine.
"""
