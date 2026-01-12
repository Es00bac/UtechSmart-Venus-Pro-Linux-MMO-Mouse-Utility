from staging_manager import StagingManager
from transaction_controller import TransactionController
from unittest.mock import MagicMock

class MockProtocol:
    def build_packets(self, key, action, params):
        print(f"[Protocol] Building packet for {key}: {action}")
        return [b'\x01']

class MockDevice:
    def send_reliable(self, packet):
        print(f"[Device] Sending packet: {packet.hex()}")
        return True

def verify():
    print("--- Verifying Phase 1: Core Logic ---")
    
    # 1. Setup
    staging = StagingManager()
    staging.load_base_state({"btn_1": {"action": "Original"}})
    
    device = MockDevice()
    protocol = MockProtocol()
    controller = TransactionController(device, protocol)
    
    # 2. Stage Change
    print("\n1. Staging 'Macro' for btn_1...")
    staging.stage_change("btn_1", "Macro", {"index": 1})
    
    if staging.has_changes():
        print("   [Pass] Staging has changes.")
    else:
        print("   [Fail] Staging empty.")
        return

    # 3. Execute Transaction
    print("\n2. Executing Transaction...")
    success = controller.execute_transaction(staging)
    
    if success:
        print("   [Pass] Transaction successful.")
    else:
        print("   [Fail] Transaction failed.")
        return

    # 4. Verify Commit
    print("\n3. Verifying Commit...")
    if not staging.has_changes():
        print("   [Pass] Staging cleared.")
    else:
        print("   [Fail] Staging not cleared.")
        
    state = staging.get_all_effective_state()
    if state["btn_1"]["action"] == "Macro":
        print("   [Pass] Base state updated to 'Macro'.")
    else:
        print(f"   [Fail] Base state is {state['btn_1']['action']}")

if __name__ == "__main__":
    verify()
