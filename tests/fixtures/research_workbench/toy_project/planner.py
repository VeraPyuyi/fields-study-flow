"""Original demonstration only. Importing this file is not required for study."""


def apply_action(state, required, added):
    """Reject missing preconditions in the toy planning example."""
    if not set(required).issubset(state):
        return None
    return set(state) | set(added)


class ToyPlanner:
    def transition(self, state):
        return apply_action(state, ["ready"], ["done"])
