import unittest
from unittest.mock import MagicMock, call
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from transaction_controller import TransactionController
from staging_manager import StagingManager

class TestTransactionController(unittest.TestCase):
    def setUp(self):
        self.mock_device = MagicMock()
        self.mock_protocol = MagicMock()
        self.staging = StagingManager()
        
        # Setup initial state
        self.staging.load_base_state({
            "btn_1": {"action": "Left Click", "params": {}},
            "btn_2": {"action": "Right Click", "params": {}},
        })
        
        self.controller = TransactionController(self.mock_device, self.mock_protocol)

    def test_execute_success(self):
        """Test successful execution of a staged transaction."""
        # Stage a change
        self.staging.stage_change("btn_1", "Macro", {"index": 1})
        
        # Mock protocol to return dummy packets
        self.mock_protocol.build_packets.return_value = [b'\x01', b'\x02']
        self.mock_device.send_reliable.return_value = True
        
        # Execute
        success = self.controller.execute_transaction(self.staging)
        
        self.assertTrue(success)
        # Should have called build_packets for btn_1
        self.mock_protocol.build_packets.assert_called_with("btn_1", "Macro", {"index": 1})
        # Should have sent packets
        self.mock_device.send_reliable.assert_has_calls([call(b'\x01'), call(b'\x02')])
        # Should have committed staging
        self.assertFalse(self.staging.has_changes())

    def test_execute_failure(self):
        """Test that execution stops on failure and does NOT commit."""
        self.staging.stage_change("btn_1", "Macro", {"index": 1})
        self.staging.stage_change("btn_2", "Middle Click", {})
        
        self.mock_protocol.build_packets.return_value = [b'\x01']
        # Fail the send
        self.mock_device.send_reliable.return_value = False
        
        success = self.controller.execute_transaction(self.staging)
        
        self.assertFalse(success)
        # Should not have committed
        self.assertTrue(self.staging.has_changes())

    def test_execute_empty(self):
        """Test execution with no changes does nothing."""
        success = self.controller.execute_transaction(self.staging)
        self.assertTrue(success)
        self.mock_device.send_reliable.assert_not_called()

if __name__ == '__main__':
    unittest.main()