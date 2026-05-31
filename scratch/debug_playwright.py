import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
from typer.testing import CliRunner
from epi_cli.main import app as cli_app
from tests.helpers.artifacts import make_decision_epi
from playwright.sync_api import sync_playwright

def debug():
    tmp_path = Path("C:/Users/dell/epi-recorder/scratch/tmp_test")
    import shutil
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir(parents=True, exist_ok=True)
    
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    extract_dir = tmp_path / "viewer"
    runner = CliRunner()
    result = runner.invoke(cli_app, ["view", str(artifact), "--extract", str(extract_dir)])
    print("CLI exit code:", result.exit_code)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        def handle_console(msg):
            print(f"BROWSER CONSOLE: {msg.type}: {msg.text}")
            
        page.on("console", handle_console)
        page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err}"))
        
        uri = (extract_dir / "viewer.html").as_uri()
        print("Loading URI:", uri)
        page.goto(uri)
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text()
        print("---------------- BODY TEXT ----------------")
        print(body.encode('ascii', errors='replace').decode('ascii'))
        print("-------------------------------------------")
        browser.close()

if __name__ == "__main__":
    debug()
