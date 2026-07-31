class QUBOFormulation:

    def __init__(self, network):

        self.network = network
        self.towers = network["towers"]

    # ----------------------------------------
    # Compute Cost Function
    # ----------------------------------------

    def compute_cost(self):

        qubo_matrix = []

        for tower in self.towers:

            utilization = tower["utilization"]

            energy = tower["energy_cost"]

            latency = tower["latency"]

            cost = (
                0.5 * utilization +
                0.3 * energy +
                0.2 * latency
            )

            tower["qubo_cost"] = round(cost, 2)

            qubo_matrix.append({
                "tower_id": tower["tower_id"],
                "cost": round(cost, 2)
            })

        self.network["qubo_matrix"] = qubo_matrix

        return self.network