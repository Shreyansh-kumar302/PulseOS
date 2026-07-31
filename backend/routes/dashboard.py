from fastapi import APIRouter

from core.network_generator import TelecomNetworkGenerator
from core.digital_twin import DigitalTwin
from core.feature_engineering import FeatureEngineering

from optimization.qubo import QUBOFormulation
from optimization.qpiai_optimizer import QpiAIOptimizer

from metrics.metrics_engine import MetricsEngine

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/")
def dashboard():

    # Generate Network
    generator = TelecomNetworkGenerator()
    network = generator.generate_network()

    # Digital Twin
    digital = DigitalTwin(network)
    network = digital.build()

    # Feature Engineering
    feature = FeatureEngineering(network)
    network = feature.build()

    # QUBO
    qubo = QUBOFormulation(network)
    network = qubo.compute_cost()

    # Optimizer
    optimizer = QpiAIOptimizer(network)
    network = optimizer.solve()

    # Metrics
    metrics = MetricsEngine(network)
    network = metrics.calculate()

    return {
        "status": "success",
        "dashboard": {
            "metrics": network["metrics"],
            "optimization": network["optimization_result"]
        }
    }