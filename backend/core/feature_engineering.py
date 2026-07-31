import math


class FeatureEngineering:

    def __init__(self, network):

        self.network = network

        self.towers = network["towers"]

        self.users = network["users"]

    # ---------------------------------------
    # Tower Utilization
    # ---------------------------------------

    def tower_utilization(self):

        for tower in self.towers:

            utilization = (

                tower["current_users"]

                /

                tower["capacity"]

            ) * 100

            tower["utilization"] = round(utilization, 2)

    # ---------------------------------------
    # Congestion Score
    # ---------------------------------------

    def congestion_score(self):

        for tower in self.towers:

            score = tower["utilization"]

            if score > 100:

                score = 100

            tower["congestion_score"] = round(score, 2)

    # ---------------------------------------
    # Energy Cost
    # ---------------------------------------

    def energy_cost(self):

        for tower in self.towers:

            energy = (

                tower["energy_consumption"]

                *

                (tower["utilization"] / 100)

            )

            tower["energy_cost"] = round(energy, 2)

    # ---------------------------------------
    # Latency Estimation
    # ---------------------------------------

    def latency_estimation(self):

        for tower in self.towers:

            latency = (

                15

                +

                tower["utilization"] * 0.35

            )

            tower["latency"] = round(latency, 2)

    # ---------------------------------------
    # Coverage Matrix
    # ---------------------------------------

    def coverage_matrix(self):

        for tower in self.towers:

            tower["covered_users"] = []

        for user in self.users:

            if user["assigned_tower"] is None:

                continue

            for tower in self.towers:

                if tower["tower_id"] == user["assigned_tower"]:

                    tower["covered_users"].append(

                        user["user_id"]

                    )

                    break

    # ---------------------------------------
    # Distance Matrix
    # ---------------------------------------

    def distance_matrix(self):

        matrix = {}

        for tower in self.towers:

            matrix[tower["tower_id"]] = []

            for user in self.users:

                dx = tower["x"] - user["x"]

                dy = tower["y"] - user["y"]

                distance = math.sqrt(

                    dx**2 +

                    dy**2

                )

                matrix[tower["tower_id"]].append(

                    round(distance, 2)

                )

        self.network["distance_matrix"] = matrix

    # ---------------------------------------
    # Build Features
    # ---------------------------------------

    def build(self):

        self.tower_utilization()

        self.congestion_score()

        self.energy_cost()

        self.latency_estimation()

        self.coverage_matrix()

       # self.distance_matrix()

        return self.network