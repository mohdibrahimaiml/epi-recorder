import asyncio
from pathlib import Path
from epi_recorder.async_api import record_async
import time

async def async_agent():
    async with record_async(Path("./async_test")) as rec:
        print("Async agent starting...")
        
        # Simulate async LLM calls
        tasks = []
        for i in range(3):
            task = asyncio.create_task(async_llm_call(i))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        print(f"Got {len(results)} results")
        
        return results

async def async_llm_call(idx):
    await asyncio.sleep(0.1)  # Simulate network
    return f"Response for call {idx}"

if __name__ == "__main__":
    result = asyncio.run(async_agent())
    print(f"Async test complete: {result}")


