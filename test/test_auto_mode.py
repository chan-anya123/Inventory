import requests
import time
import random

BASE_URL = "http://localhost:8000"
ITEMS = ["toy", "cookies", "bunny"]

def delay(s):
    time.sleep(s)

def get_slots_data():
    r = requests.get(f"{BASE_URL}/slots")
    if r.status_code == 200: return r.json()
    return {}

def test_auto_mode():
    data = get_slots_data()
    slots = data.get("slots", [])
    if not slots: return
    
    target = slots[0]
    point_name = target["point_name"]
    sensor_mapping = data.get("sensor_mapping", {})
    sensor_id = next((k for k, v in sensor_mapping.items() if v == point_name), f"S_{point_name}")

    print(f"[*] Targeting slot: {point_name} with sensor: {sensor_id}")

    # FORCE cancel any pending operations
    requests.post(f"{BASE_URL}/slot/cancel", json={"point_name": point_name})
    
    # Empty all items properly
    print("[*] Cleaning up slot...")
    while True:
        s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
        if not s.get("items") and s.get("status") not in ["DROP_RESERVED", "PICKUP_RESERVED"]:
            break
            
        if s.get("status") == "PICKUP_RESERVED":
            requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})
            delay(0.5)
            continue
        elif s.get("status") == "DROP_RESERVED":
            requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": True})
            delay(0.5)
            continue
            
        if s.get("items"):
            r = requests.post(f"{BASE_URL}/slot/pickup", json={"point_name": point_name, "user_id": "TEST_CLEANUP", "quantity": 1})
            if r.status_code == 200:
                requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})
                delay(0.5)

    requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})
    
    # === TEST 1: BASIC AUTO DROP & PICKUP ===
    print("\n--- Test 1: Auto Drop ---")
    requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": "cookie", "user_id": "TEST_BOT", "quantity": 1})
    s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
    assert s["status"] == "DROP_RESERVED", f"Slot should be DROP_RESERVED, but got {s['status']}"
    
    delay(1.5)
    requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": True})
    delay(1.5)
    
    s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
    assert s["status"] == "FULL", f"Expected FULL, got {s['status']}"
    print("[+] Test 1 Passed: Drop completed via sensor.")
    
    print("\n--- Test 2: Auto Pickup ---")
    requests.post(f"{BASE_URL}/slot/pickup", json={"point_name": point_name, "user_id": "TEST_BOT", "quantity": 1})
    s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
    assert s["status"] == "PICKUP_RESERVED", "Slot should be PICKUP_RESERVED"
    
    delay(1.5)
    requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})
    delay(1.5)
    
    s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
    assert s["status"] == "EMPTY", f"Expected EMPTY, got {s['status']}"
    print("[+] Test 2 Passed: Pickup completed via sensor.")

    # === TEST 3: QUEUE & LOOP BURST ===
    print("\n--- Test 3: Loop & Queue Burst in Auto Mode ---")
    print("[*] Simulating 3 fast drops to trigger queue...")
    
    # First drop goes straight to DROP_RESERVED
    requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": "cookie", "user_id": "ROBOT_0", "quantity": 1})
    
    # Next two should be queued
    for i in range(1, 3):
        item = target.get("allowed_item", ["cookie"])[0] if target.get("allowed_item") else "cookie"
        requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item, "user_id": f"ROBOT_{i}", "quantity": 1})
        print(f"  -> Requested drop for {item}")
        delay(0.2)

    s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
    assert s["status"] == "DROP_RESERVED"
    assert len(s["queue"]) == 2, f"Expected 2 items in queue, got {len(s['queue'])}"
    print("[+] Queue successfully accumulated 2 pending drops.")

    print("[*] Processing the queue using Sensor events...")
    for i in range(3):
        print(f"\n[Queue {i+1}/3] Simulating physical drop completion...")
        delay(1.0)
        requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": True})
        delay(1.5)
        
        s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
        assert s["status"] == "FULL", f"Expected FULL, got {s['status']}"
        print(f"  -> Slot is FULL with {s['items'][0]['item_type']}.")
        
        print(f"[Queue {i+1}/3] Requesting pickup for the item...")
        requests.post(f"{BASE_URL}/slot/pickup", json={"point_name": point_name, "user_id": "TEST_BOT", "quantity": 1})
        delay(0.5)
        
        s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
        assert s["status"] == "PICKUP_RESERVED"
        
        print(f"[Queue {i+1}/3] Simulating physical pickup completion...")
        delay(1.0)
        requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})
        delay(1.5)
        
        s = next((x for x in get_slots_data().get("slots", []) if x["point_name"] == point_name), None)
        if i < 2:
            assert s["status"] == "DROP_RESERVED", f"Expected DROP_RESERVED from queue, got {s['status']}"
            print("  -> Backend automatically popped the next queue item! Slot is DROP_RESERVED.")
        else:
            assert s["status"] == "EMPTY", f"Expected EMPTY, got {s['status']}"
            print("  -> Queue is empty. Slot is EMPTY.")

    print("[+] Test 3 Passed: Auto Mode Queue processing works perfectly.")
    
    print("\n[*] ALL AUTO MODE TESTS PASSED SUCCESSFULLY! ✅")

if __name__ == "__main__":
    test_auto_mode()
