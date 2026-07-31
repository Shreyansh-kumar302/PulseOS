import random
import math


class TelecomNetworkGenerator:
    """
    Generates a sample telecom network with:
    - Towers
    - Users
    - User assignment
    - Signal strength
    """

    def __init__(
        self,
        map_width=1000,
        map_height=1000,
        num_towers=10,
        num_users=100,
    ):

        self.map_width = map_width
        self.map_height = map_height

        self.num_towers = num_towers
        self.num_users = num_users

    # ---------------------------------------------------
    # Generate Towers
    # ---------------------------------------------------

    def generate_towers(self):

        towers = []

        for tower_id in range(1, self.num_towers + 1):

            tower = {
                "tower_id": tower_id,

                "x": random.randint(0, self.map_width),

                "y": random.randint(0, self.map_height),

                "coverage_radius": random.randint(120, 220),

                "capacity": random.randint(120, 250),

                "current_users": 0,

                "status": "ACTIVE",

                "energy_consumption": round(
                    random.uniform(2.5, 6.5),
                    2
                ),

                "health": 100
            }

            towers.append(tower)

        return towers

    # ---------------------------------------------------
    # Generate Users
    # ---------------------------------------------------

    def generate_users(self):

        users = []

        for user_id in range(1, self.num_users + 1):

            user = {

                "user_id": user_id,

                "x": random.randint(0, self.map_width),

                "y": random.randint(0, self.map_height),

                "traffic_demand": random.randint(1, 10),

                "assigned_tower": None,

                "signal_strength": None

            }

            users.append(user)

        return users

    # ---------------------------------------------------
    # Distance
    # ---------------------------------------------------

    def calculate_distance(
        self,
        x1,
        y1,
        x2,
        y2
    ):

        return math.sqrt(
            (x1 - x2) ** 2 +
            (y1 - y2) ** 2
        )

    # ---------------------------------------------------
    # Signal Strength
    # ---------------------------------------------------

    def calculate_signal_strength(
        self,
        distance
    ):

        signal = -30 - (0.30 * distance)

        return round(signal, 2)

    # ---------------------------------------------------
    # Assign Users To Best Tower
    # ---------------------------------------------------

    def assign_users_to_towers(
        self,
        towers,
        users
    ):

        for user in users:

            best_tower = None

            best_signal = -999

            for tower in towers:

                distance = self.calculate_distance(

                    user["x"],
                    user["y"],

                    tower["x"],
                    tower["y"]

                )

                if distance <= tower["coverage_radius"]:

                    signal = self.calculate_signal_strength(
                        distance
                    )

                    if signal > best_signal:

                        best_signal = signal

                        best_tower = tower

            if best_tower:

                user["assigned_tower"] = best_tower["tower_id"]

                user["signal_strength"] = best_signal

                best_tower["current_users"] += 1

        return towers, users

    # ---------------------------------------------------
    # Generate Complete Network
    # ---------------------------------------------------

    def generate_network(self):

        towers = self.generate_towers()

        users = self.generate_users()

        towers, users = self.assign_users_to_towers(
            towers,
            users
        )

        network = {

            "towers": towers,

            "users": users

        }

        return network