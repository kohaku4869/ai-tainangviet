from .state import AgentState, InputState, OutputState

__all__ = ["AgentState", "InputState", "OutputState", "build_graph", "graph"]


def __getattr__(name: str):
    # Nạp builder khi cần (PEP 562): nodes import graph.state, còn builder import nodes -> tránh import vòng.
    if name in ("graph", "build_graph"):
        from . import builder

        return getattr(builder, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
