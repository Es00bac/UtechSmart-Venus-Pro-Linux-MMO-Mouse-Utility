class TransactionController:
    """Send staged changes sequentially and update local state on success.

    Areson EEPROM writes persist as soon as each packet is acknowledged, so
    this is deliberately not described as an atomic transaction: a failure can
    leave the successfully written prefix on the device.
    """
    def __init__(self, device, packet_builder, logger=None):
        """
        device: VenusDevice instance (must support send_reliable)
        packet_builder: Object with build_packets(key, action, params) method
        logger: Optional callable that accepts a string message
        """
        self.device = device
        self.builder = packet_builder
        self.logger = logger

    def _log(self, msg: str):
        if self.logger:
            self.logger(msg)

    def execute_transaction(self, staging_manager) -> bool:
        """
        Apply all staged changes to the device.
        Returns True if successful, False if any packet failed.
        Commits the staging manager on success.
        """
        if not staging_manager.has_changes():
            self._log("TransactionController: No changes to apply.")
            return True

        changes = staging_manager.get_staged_changes()
        all_packets = []
        
        self._log(f"TransactionController: Preparing to apply {len(changes)} changes...")

        # 1. Build all packets first (Fail early on build error)
        try:
            for key, data in changes.items():
                action = data["action"]
                params = data["params"]
                packets = self.builder.build_packets(key, action, params)
                all_packets.extend(packets)
        except Exception as e:
            self._log(f"TransactionController: Build error: {e}")
            return False

        self._log(f"TransactionController: Built {len(all_packets)} packets. Sending...")

        # 2. Send packets. Each successful ACK may already represent a
        # persistent EEPROM change.
        for i, pkt in enumerate(all_packets):
            if not self.device.send_reliable(pkt):
                self._log(f"TransactionController: Send failed at packet {i}/{len(all_packets)} ({pkt.hex()})")
                return False
            # Optional: Detailed logging for every packet might be too noisy, 
            # but good for debug. Let's log every 5th or on error.
            if i % 5 == 0:
                self._log(f"TransactionController: Sent packet {i+1}/{len(all_packets)}")

        # 3. Update the application's base state only after all ACKs.
        self._log("TransactionController: All packets acknowledged; updating local state.")
        staging_manager.commit()
        return True
