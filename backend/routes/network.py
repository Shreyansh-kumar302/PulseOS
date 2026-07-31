from fastapi import APIRouter

from core.network_generator import TelecomNetworkGenerator
from core.digital_twin import DigitalTwin
from core.feature_engineering import FeatureEngineering

from optimization.qubo import QUBOFormulation
from optimization.qpiai_optimizer import QpiAIOptimizer

from metrics.metrics_engine import MetricsEngine

router = APIRouter(
    prefix="/network",
    tags=["Network"]
)


@router.get("/generate")
def generate_network():

    # Step 1 - Generate Network
    generator = TelecomNetworkGenerator()
    network = generator.generate_network()

    # Step 2 - Digital Twin
    digital = DigitalTwin(network)
    network = digital.build()

    # Step 3 - Feature Engineering
    feature = FeatureEngineering(network)
    network = feature.build()

    # Step 4 - QUBO
    qubo = QUBOFormulation(network)
    network = qubo.compute_cost()

    # Step 5 - Optimizer
    optimizer = QpiAIOptimizer(network)
    network = optimizer.solve()

    # Step 6 - Metrics
    metrics = MetricsEngine(network)
    network = metrics.calculate()

    # Final Response
    return {
        "status": "success",
        "metrics": network["metrics"],
        "optimization": network["optimization_result"]
    }