import numpy as np

class QuboFormulation:
    """Formulates telecom network allocation problems into Quadratic Unconstrained Binary Optimization (QUBO)."""
    def __init__(self):
        pass

    def build_matrix(self, num_vars):
        """Builds a random QUBO matrix for demo purposes."""
        # Q matrix should be symmetric/upper-triangular
        Q = np.random.uniform(-1, 1, size=(num_vars, num_vars))
        Q = (Q + Q.T) / 2
        return Q.tolist()
