import os
import sys
from pathlib import Path

# Ensure working directory is repository root
repo_root = Path(__file__).resolve().parent.parent
os.chdir(repo_root)

from epi_guardrails import instrument, uninstrument

# Instrument Guardrails
output_epi = Path('test_guardrails_output.epi')
instrument(output_path=output_epi)

# Define a rail string
rail = """
<rail version="0.1">
<output>
    <string name="test" description="A simple test string" />
</output>
</rail>
"""

from guardrails import Guard

# Create Guard instance
guard = Guard.for_rail_string(rail)

# Mock API function
def mock_llm_api(*args, **kwargs):
    return "hello world"

# Execute guard using the call pattern that should trigger Runner.step
try:
    # In 0.10.x, the standard way is response = guard(api, prompt_params, ...)
    result = guard(
        mock_llm_api,
        prompt_params={},
        messages=[{"role": "user", "content": "hi"}]
    )
    print('Guard result:', result)
except Exception as e:
    print(f'Guard execution failed: {e}')
    import traceback
    traceback.print_exc()

# Uninstrument
uninstrument()

# Verify the .epi file exists and count steps
if output_epi.exists():
    from epi_core.container import EPIContainer
    steps = EPIContainer.count_steps(output_epi)
    print(f'Step count in .epi artifact: {steps}')
    
    # Read manifest to check source metadata
    manifest = EPIContainer.read_manifest(output_epi)
    print(f'Manifest Goals: {manifest.goal}')
    print(f'Source Integration: {manifest.source.get("integration") if manifest.source else "N/A"}')
else:
    print('.epi artifact not found')
