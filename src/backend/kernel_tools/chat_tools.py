import json
from typing import Callable, Dict


class ChatTools:
    """Utility placeholder for chat agent metadata."""

    agent_name = "Chat_Agent"

    @classmethod
    def get_all_kernel_functions(cls) -> Dict[str, Callable]:
        # ChatAgent handles queries programmatically; no kernel functions required.
        return {}

    @classmethod
    def generate_tools_json_doc(cls) -> str:
        """Return an empty tool declaration for planner compatibility."""

        return json.dumps([])
