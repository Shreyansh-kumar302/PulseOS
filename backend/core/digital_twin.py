class DigitalTwin:
    """
    Creates a live digital representation of the telecom network.
    """

    def __init__(self, network):

        self.network = network

        self.towers = network["towers"]

        self.users = network["users"]

    # --------------------------------------
    # Calculate Tower Utilization
    # --------------------------------------

    def calculate_utilization(self):

        for tower in self.towers:

            capacity = tower["capacity"]

            current = tower["current_users"]

            utilization = (current / capacity) * 100

            tower["utilization"] = round(utilization, 2)

        return self.towers

    # --------------------------------------
    # Detect Tower Status
    # --------------------------------------

    def update_tower_status(self):

        for tower in self.towers:

            utilization = tower["utilization"]

            if utilization >= 100:

                tower["network_state"] = "OVERLOADED"

            elif utilization >= 80:

                tower["network_state"] = "HIGH_LOAD"

            elif utilization >= 40:

                tower["network_state"] = "NORMAL"

            else:

                tower["network_state"] = "LOW_LOAD"

        return self.towers

    # --------------------------------------
    # Calculate Available Capacity
    # --------------------------------------

    def available_capacity(self):

        for tower in self.towers:

            tower["available_capacity"] = (

                tower["capacity"]

                -

                tower["current_users"]

            )

        return self.towers

    # --------------------------------------
    # Build Digital Twin
    # --------------------------------------

    def build(self):

        self.calculate_utilization()

        self.update_tower_status()

        self.available_capacity()

        return {

            "towers": self.towers,

            "users": self.users

        }