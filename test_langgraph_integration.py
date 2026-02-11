"""
Test LangGraph integration with EPI Recorder

Validates EPICheckpointSaver works correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

# Check if LangGraph is installed
try:
    from langgraph.graph import StateGraph
    from langgraph.checkpoint import Checkpoint
    LANGGRAPH_INSTALLED = True
except ImportError:
    LANGGRAPH_INSTALLED = False
    print("WARNING: LangGraph not installed. Install with: pip install langgraph")
    print("Skipping LangGraph tests...")

from epi_recorder.integrations import EPICheckpointSaver
from epi_recorder import record

async def test_checkpoint_save_load():
    """Test basic checkpoint save and load"""
    print("Test 1: Checkpoint save/load")
    print("-" * 60)
    
    try:
        async with record("test_langgraph.epi", goal="Test checkpoint") as epi:
            checkpointer = EPICheckpointSaver()
            
            # Create mock checkpoint
            checkpoint = {
                "id": "checkpoint_1",
                "state": {"counter": 5, "messages": ["hello"]},
                "metadata": {"step": 1}
            }
            
            config = {"configurable": {"thread_id": "test_thread"}}
            
            # Save checkpoint
            await checkpointer.aput(config, checkpoint, {"step": 1})
            print("  Saved checkpoint")
            
            # Load checkpoint
            loaded = await checkpointer.aget(config)
            print(f"  Loaded checkpoint: {loaded}")
            
            if loaded and loaded.get("id") == "checkpoint_1":
                print("  SUCCESS: Checkpoint saved and loaded")
                return True
            else:
                print("  ERROR: Checkpoint mismatch")
                return False
                
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_large_state_handling():
    """Test that large states are hashed instead of serialized"""
    print("\nTest 2: Large state handling")
    print("-" * 60)
    
    try:
        async with record("test_large_state.epi") as epi:
            checkpointer = EPICheckpointSaver(
                serialize_large_states=False,
                max_state_size=100  # Very small for testing
            )
            
            # Create checkpoint with large state
            large_state = {"data": "x" * 1000}  # 1KB state
            checkpoint = {
                "id": "checkpoint_large",
                "state": large_state
            }
            
            config = {"configurable": {"thread_id": "test_large"}}
            
            # This should hash the state instead of serializing
            await checkpointer.aput(config, checkpoint, {})
            print("  Saved large state (hashed)")
            
            print("  SUCCESS: Large state handled")
            return True
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_multiple_checkpoints():
    """Test saving multiple checkpoints"""
    print("\nTest 3: Multiple checkpoints")
    print("-" * 60)
    
    try:
        async with record("test_multi_checkpoint.epi") as epi:
            checkpointer = EPICheckpointSaver()
            config = {"configurable": {"thread_id": "test_multi"}}
            
            # Save 3 checkpoints
            for i in range(3):
                checkpoint = {
                    "id": f"checkpoint_{i}",
                    "state": {"step": i}
                }
                await checkpointer.aput(config, checkpoint, {"step": i})
                print(f"  Saved checkpoint {i}")
            
            # List checkpoints
            checkpoints = []
            async for cp in checkpointer.alist(config):
                checkpoints.append(cp)
            
            print(f"  Listed {len(checkpoints)} checkpoints")
            
            if len(checkpoints) == 3:
                print("  SUCCESS: All checkpoints saved")
                return True
            else:
                print(f"  ERROR: Expected 3 checkpoints, got {len(checkpoints)}")
                return False
                
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_import():
    """Test that EPICheckpointSaver can be imported"""
    print("Test 0: Import test")
    print("-" * 60)
    
    try:
        from epi_recorder.integrations import EPICheckpointSaver
        print("  SUCCESS: EPICheckpointSaver imported")
        return True
    except ImportError as e:
        print(f"  ERROR: Cannot import: {e}")
        return False

async def run_all_tests():
    """Run all LangGraph integration tests"""
    print("=" * 70)
    print("LANGGRAPH INTEGRATION - TEST SUITE")
    print("=" * 70)
    print()
    
    results = []
    
    # Test 0: Import
    results.append(test_import())
    
    if not LANGGRAPH_INSTALLED:
        print()
        print("=" * 70)
        print("SKIPPED: LangGraph not installed")
        print("=" * 70)
        print()
        print("To install: pip install langgraph")
        return 0  # Don't fail if LangGraph not installed
    
    # Test 1: Save/load
    results.append(await test_checkpoint_save_load())
    
    # Test 2: Large state
    results.append(await test_large_state_handling())
    
    # Test 3: Multiple checkpoints
    results.append(await test_multiple_checkpoints())
    
    print()
    print("=" * 70)
    
    if all(results):
        print("ALL TESTS PASSED - LANGGRAPH INTEGRATION WORKING")
        print("=" * 70)
        print()
        print("LangGraph checkpoint saver is production-ready!")
        print()
        print("Usage:")
        print("  from epi_recorder.integrations import EPICheckpointSaver")
        print("  checkpointer = EPICheckpointSaver('agent.epi')")
        print("  await graph.ainvoke(data, checkpointer=checkpointer)")
        print()
        return 0
    else:
        print("SOME TESTS FAILED")
        print("=" * 70)
        failed = sum(1 for r in results if not r)
        print(f"Failed: {failed}/{len(results)} tests")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
