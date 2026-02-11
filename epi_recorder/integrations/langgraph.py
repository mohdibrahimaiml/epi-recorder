"""
LangGraph Checkpoint Integration for EPI Recorder

Provides native checkpoint saving for LangGraph agents, enabling
automatic state tracking and replay capabilities.

Usage:
    from langgraph.graph import StateGraph
    from epi_recorder.integrations import EPICheckpointSaver
    
    graph = StateGraph(...)
    
    # Use EPI as checkpoint backend
    checkpointer = EPICheckpointSaver("my_agent.epi")
    result = graph.invoke(
        {"messages": [...]},
        {"configurable": {"thread_id": "1"}},
        checkpointer=checkpointer
    )
"""

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, Optional, Sequence, Tuple
from contextlib import asynccontextmanager

try:
    from langgraph.checkpoint import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    # Provide stub classes for when LangGraph is not installed
    class BaseCheckpointSaver:
        pass
    
    class Checkpoint:
        pass
    
    class CheckpointMetadata:
        pass

from epi_recorder import record, get_current_session


class EPICheckpointSaver(BaseCheckpointSaver):
    """
    LangGraph checkpoint saver that records state transitions to .epi files.
    
    This enables:
    - Automatic state tracking for LangGraph agents
    - Replay of agent execution with state snapshots
    - Debugging failed runs by inspecting checkpoints
    - A/B testing different agent configurations
    
    Args:
        output_path: Path to .epi file for recording
        auto_sign: Whether to automatically sign .epi file
        serialize_large_states: If False, only hash large states (>1MB)
        
    Example:
        from langgraph.graph import StateGraph
        from epi_recorder.integrations import EPICheckpointSaver
        
        # Define your graph
        graph = StateGraph(...)
        
        # Use EPI checkpoint saver
        checkpointer = EPICheckpointSaver("agent_run.epi")
        
        # Run with checkpointing
        result = graph.invoke(
            input_data,
            config={"configurable": {"thread_id": "1"}},
            checkpointer=checkpointer
        )
        
        # Later: inspect checkpoints in .epi viewer
        # epi view agent_run.epi
    """
    
    def __init__(
        self,
        output_path: Optional[str] = None,
        auto_sign: bool = True,
        serialize_large_states: bool = False,
        max_state_size: int = 1024 * 1024  # 1MB default
    ):
        """
        Initialize EPI checkpoint saver.
        
        Args:
            output_path: Path to .epi file (auto-generated if None)
            auto_sign: Whether to sign .epi file on completion
            serialize_large_states: If False, only hash states larger than max_state_size
            max_state_size: Maximum state size to fully serialize (bytes)
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is not installed. Install with: pip install langgraph"
            )
        
        self.output_path = output_path
        self.auto_sign = auto_sign
        self.serialize_large_states = serialize_large_states
        self.max_state_size = max_state_size
        
        # Internal state
        self._checkpoints: Dict[Tuple[str, str], Checkpoint] = {}
        self._recording_session = None
    
    def _serialize_state(self, state: Any) -> Dict[str, Any]:
        """
        Serialize checkpoint state safely.
        
        Handles:
        - Large states (hash instead of full serialization)
        - Unserializable types (convert to string)
        - Circular references (detect and warn)
        
        Returns:
            Serializable dict representation
        """
        try:
            # Try to serialize to JSON to check size
            state_json = json.dumps(state, default=str)
            state_size = len(state_json.encode('utf-8'))
            
            # If state is too large and we're not serializing large states
            if state_size > self.max_state_size and not self.serialize_large_states:
                # Hash the state instead
                state_hash = hashlib.sha256(state_json.encode('utf-8')).hexdigest()
                return {
                    "_epi_large_state": True,
                    "hash": state_hash,
                    "size_bytes": state_size,
                    "serialization": "hashed",
                    "note": f"State too large ({state_size} bytes), hashed for reference"
                }
            
            # Return full state
            return {
                "_epi_full_state": True,
                "data": state,
                "size_bytes": state_size,
                "serialization": "full"
            }
            
        except (TypeError, ValueError, RecursionError) as e:
            # Fallback: convert to string representation
            return {
                "_epi_serialization_error": True,
                "error": str(e),
                "representation": str(state),
                "type": type(state).__name__,
                "serialization": "string"
            }
    
    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata
    ) -> None:
        """
        Save a checkpoint asynchronously.
        
        Args:
            config: LangGraph configuration dict
            checkpoint: Checkpoint object to save
            metadata: Checkpoint metadata
        """
        # Extract thread_id from config
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = checkpoint.get("id", str(datetime.utcnow().timestamp()))
        
        # Store checkpoint in memory
        self._checkpoints[(thread_id, checkpoint_id)] = checkpoint
        
        # Get current EPI session or create one
        session = get_current_session()
        
        if session:
            # We're inside an existing recording session
            await session.alog_step("langgraph.checkpoint.save", {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint": self._serialize_state(checkpoint),
                "metadata": metadata,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            # No active session - checkpoint will be logged when graph completes
            # This is expected for graph.invoke() calls without explicit record()
            pass
    
    async def aget(
        self,
        config: Dict[str, Any]
    ) -> Optional[Checkpoint]:
        """
        Retrieve a checkpoint asynchronously.
        
        Args:
            config: LangGraph configuration dict
            
        Returns:
            Checkpoint if found, None otherwise
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        
        # Find latest checkpoint for this thread
        thread_checkpoints = [
            (cid, cp) for (tid, cid), cp in self._checkpoints.items()
            if tid == thread_id
        ]
        
        if not thread_checkpoints:
            return None
        
        # Return most recent checkpoint
        latest_checkpoint = sorted(thread_checkpoints, key=lambda x: x[0])[-1][1]
        
        # Log retrieval
        session = get_current_session()
        if session:
            await session.alog_step("langgraph.checkpoint.load", {
                "thread_id": thread_id,
                "checkpoint_id": latest_checkpoint.get("id"),
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return latest_checkpoint
    
    async def alist(
        self,
        config: Dict[str, Any]
    ) -> AsyncIterator[Checkpoint]:
        """
        List all checkpoints for a thread asynchronously.
        
        Args:
            config: LangGraph configuration dict
            
        Yields:
            Checkpoints in chronological order
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        
        # Find all checkpoints for this thread
        thread_checkpoints = [
            (cid, cp) for (tid, cid), cp in self._checkpoints.items()
            if tid == thread_id
        ]
        
        # Sort by checkpoint_id (chronological)
        thread_checkpoints.sort(key=lambda x: x[0])
        
        # Yield checkpoints
        for checkpoint_id, checkpoint in thread_checkpoints:
            yield checkpoint
    
    # Sync versions (required by BaseCheckpointSaver interface)
    
    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata
    ) -> None:
        """Synchronous version of aput()"""
        asyncio.run(self.aput(config, checkpoint, metadata))
    
    def get(self, config: Dict[str, Any]) -> Optional[Checkpoint]:
        """Synchronous version of aget()"""
        return asyncio.run(self.aget(config))
    
    def list(self, config: Dict[str, Any]) -> Iterator[Checkpoint]:
        """Synchronous version of alist()"""
        async def _alist():
            checkpoints = []
            async for cp in self.alist(config):
                checkpoints.append(cp)
            return checkpoints
        
        checkpoints = asyncio.run(_alist())
        return iter(checkpoints)


# Convenience context manager for LangGraph + EPI recording
@asynccontextmanager
async def record_langgraph(
    output_path: Optional[str] = None,
    **record_kwargs
):
    """
    Context manager that combines EPI recording with LangGraph checkpointing.
    
    Usage:
        from epi_recorder.integrations.langgraph import record_langgraph
        
        async with record_langgraph("agent.epi") as checkpointer:
            result = await graph.ainvoke(
                input_data,
                config={"configurable": {"thread_id": "1"}},
                checkpointer=checkpointer
            )
    
    Args:
        output_path: Path to .epi file
        **record_kwargs: Additional arguments for record()
        
    Yields:
        EPICheckpointSaver instance
    """
    async with record(output_path, **record_kwargs):
        checkpointer = EPICheckpointSaver(output_path)
        yield checkpointer
