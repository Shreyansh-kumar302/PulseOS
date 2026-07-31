class MetricsEngine:

    def __init__(self, network):

        self.network = network
        self.towers = network["towers"]
        self.users = network["users"]

    def calculate(self):

        total_towers = len(self.towers)

        active_towers = sum(
            1 for tower in self.towers
            if tower["status"] == "ACTIVE"
        )

        connected_users = sum(
            1 for user in self.users
            if user["assigned_tower"] is not None
        )

        avg_utilization = round(

            sum(

                tower["utilization"]

                for tower in self.towers

            ) / total_towers,

            2

        )

        avg_latency = round(

            sum(

                tower["latency"]

                for tower in self.towers

            ) / total_towers,

            2

        )

        avg_energy = round(

            sum(

                tower["energy_cost"]

                for tower in self.towers

            ) / total_towers,

            2

        )

        overloaded = sum(

            1 for tower in self.towers

            if tower["network_state"] == "OVERLOADED"

        )

        metrics = {

            "total_towers": total_towers,

            "active_towers": active_towers,

            "total_users": len(self.users),

            "connected_users": connected_users,

            "average_utilization": avg_utilization,

            "average_latency": avg_latency,

            "average_energy_cost": avg_energy,

            "overloaded_towers": overloaded

        }

        self.network["metrics"] = metrics

        return self.network
