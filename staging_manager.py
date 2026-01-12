from copy import deepcopy

class StagingManager:
    """
    Manages the staging of button assignment changes.
    Separates the 'committed' state (on device) from the 'staged' state (in UI).
    """
    def __init__(self):
        self.base_state = {}
        self.staged_state = {}

    def load_base_state(self, state: dict):
        """
        Load the authoritative state from the device/application.
        Clears any existing staged changes.
        """
        self.base_state = deepcopy(state)
        self.staged_state = {}

    def stage_change(self, key: str, action: str, params: dict):
        """
        Stage a change for a specific button key.
        """
        self.staged_state[key] = {"action": action, "params": params}

    def get_effective_state(self, key: str) -> dict | None:
        """
        Get the state of a key, preferring staged over base.
        """
        if key in self.staged_state:
            return self.staged_state[key]
        return self.base_state.get(key)

    def get_all_effective_state(self) -> dict:
        """
        Return the complete state map with staged changes applied.
        """
        state = deepcopy(self.base_state)
        state.update(self.staged_state)
        return state

    def clear_stage(self):
        """Discard all staged changes."""
        self.staged_state = {}

    def commit(self):
        """
        Apply staged changes to base state.
        Call this after successful device sync.
        """
        self.base_state.update(self.staged_state)
        self.staged_state = {}

    def get_staged_changes(self) -> dict:
        """Return dictionary of only the staged items."""
        return self.staged_state

    def has_changes(self) -> bool:
        """Return True if there are pending changes."""
        return len(self.staged_state) > 0
