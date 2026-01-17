import requests
import time
import sys
import json

def test_gateway():
    print("EPI Enterprise Gateway Manual Check")
    print("--------------------------------------")
    
    url = "http://127.0.0.1:8000/capture"
    payload = {
        "kind": "manual_test",
        "content": {"command": "echo 'Manual Audit Log Entry'"},
        "meta": {"context": "User_Self_Test", "tags": ["manual", "test"]}
    }

    print(f"Sending Request to: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        start_time = time.time()
        response = requests.post(url, json=payload)
        end_time = time.time()
        
        duration_ms = (end_time - start_time) * 1000

        if response.status_code == 202:
            print(f"SUCCESS! Response received in {duration_ms:.2f}ms")
            print(f"Server says: {response.json()}")
            print("\nCHECKING EVIDENCE:")
            print("   Go to your 'evidence_vault' folder.")
            print("   You should see a new .json file created just now (after 2s delay).")
        else:
            print(f"FAILED. Status Code: {response.status_code}")
            print(f"   Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print("\nCONNECTION FAILED")
        print("   The Gateway server is NOT running.")
        print("   Please open a NEW terminal and run:")
        print("   -----------------------------------")
        print("   uvicorn epi_gateway.main:app --reload")
        print("   -----------------------------------")
        print("   Then run this script again.")

if __name__ == "__main__":
    test_gateway()
