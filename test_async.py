import asyncio
from epi_recorder.async_api import record_async

async def test_async():
    print("Starting Async Test...")
    async with record_async("test_async", ".") as rec:
        # This should NOT hang
        print("Recording step...")
        await rec.record_step("test", {"msg": "hello"})
        await asyncio.sleep(0.1)  # Simulate async work
        print("Success!")

if __name__ == "__main__":
    asyncio.run(test_async())


