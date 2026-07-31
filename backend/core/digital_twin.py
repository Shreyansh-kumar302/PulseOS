class DigitalTwin:
    """Represents the digital twin of the telecom network environment."""
    def __init__(self):
        self.state = {}

    def sync_state(self, real_world_telemetry):
        """Synchronizes the digital twin state with physical network telemetry."""
        self.state = real_world_telemetry
        return self.state

    def get_state(self):
        return self.state
