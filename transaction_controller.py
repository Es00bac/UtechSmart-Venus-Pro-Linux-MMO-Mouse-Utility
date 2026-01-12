class TransactionController:
    """
    Orchestrates the application of staged changes to the device.
    Ensures atomicity by attempting to send all packets and only committing
    the stage if successful.
    """
    def __init__(self, device, packet_builder):
        """
        device: VenusDevice instance (must support send_reliable)
        packet_builder: Object with build_packets(key, action, params) method
        """
        self.device = device
        self.builder = packet_builder

    def execute_transaction(self, staging_manager) -> bool:
        """
        Apply all staged changes to the device.
        Returns True if successful, False if any packet failed.
        Commits the staging manager on success.
        """
        if not staging_manager.has_changes():
            return True

        changes = staging_manager.get_staged_changes()
        all_packets = []

        # 1. Build all packets first (Fail early on build error)
        try:
            for key, data in changes.items():
                action = data["action"]
                params = data["params"]
                packets = self.builder.build_packets(key, action, params)
                all_packets.extend(packets)
        except Exception:
            # TODO: Log error
            return False

        # 2. Send packets
        # In a real atomic setup, we might want to verify state, but 
        # for HID, reliable send is our best proxy.
        for pkt in all_packets:
            if not self.device.send_reliable(pkt):
                return False

        # 3. Commit state on success
        staging_manager.commit()
        return True
