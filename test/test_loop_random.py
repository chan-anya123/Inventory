import requests
import time
import random

BASE_URL = "http://localhost:8000"
ITEMS = ["cookie", "box", "empty pallet"]
USERS = ["USER_A", "USER_B", "USER_C"]
ITERATIONS = 20

def log(msg):
    print(f"[*] {msg}")
    
def delay(sec=5.0):
    sec = sec * 3  # Triple the wait time for easier debugging
    log(f"Waiting {sec}s...")
    time.sleep(sec)

def get_slots():
    resp = requests.get(f"{BASE_URL}/slots")
    if resp.status_code == 200:
        return resp.json().get("slots", [])
    return []

def run_loop():
    log("Starting Pick/Place & Queue Loop Test...")
    for i in range(1, ITERATIONS + 1):
        log(f"\n--- Iteration {i}/{ITERATIONS} ---")
        slots = get_slots()
        
        # 33% Drop, 33% Pickup, 33% Queue Burst
        action = random.choice(["DROP", "PICKUP", "QUEUE_DROP"])
        
        if action == "DROP":
            item = random.choice(ITEMS)
            user = random.choice(USERS)
            log(f"Action: DROP -> Item: {item} by {user}")
            
            target_slot = None
            for s in slots:
                if not s.get("enabled", True): continue
                if max(0, int(s.get("max_capacity", 1)) - len(s.get("items", []))) <= 0: continue
                allowed = s.get("allowed_item", [])
                if isinstance(allowed, list) and allowed and "*" not in allowed and item not in allowed: continue
                target_slot = s
                break
                
            if not target_slot:
                log(f"No available slot for {item}. Skipping.")
                continue
                
            point_name = target_slot["point_name"]
            resp = requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item, "user_id": user, "quantity": 1})
            log(f"Drop response: {resp.json().get('status')}")
            
            delay(1.5)
            requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
            log("Drop confirmed.")
            
        elif action == "PICKUP":
            user = random.choice(USERS)
            log(f"Action: PICKUP by {user}")
            
            full_slots = [s for s in slots if s.get("status") == "FULL" and s.get("enabled", True)]
            if not full_slots:
                log("No full slots in inventory to pickup. Skipping.")
                continue
                
            target_slot = random.choice(full_slots)["point_name"]
            resp = requests.post(f"{BASE_URL}/slot/pickup", json={"point_name": target_slot, "user_id": user, "quantity": 1})
            log(f"Pickup response: {resp.json().get('status')} at {target_slot}")
            
            if resp.status_code == 200:
                delay(1.5)
                requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": target_slot})
                log("Pickup confirmed.")
                
        elif action == "QUEUE_DROP":
            item = random.choice(ITEMS)
            log(f"Action: QUEUE_DROP -> Bursting 3 drops for {item} into the SAME slot to test queue!")
            
            # Find an empty slot
            target_slot = None
            for s in slots:
                if s.get("status") == "EMPTY" and s.get("enabled", True):
                    allowed = s.get("allowed_item", [])
                    if isinstance(allowed, list) and allowed and "*" not in allowed and item not in allowed: continue
                    target_slot = s
                    break
            
            if not target_slot:
                log("No empty slot available for burst drop. Skipping.")
                continue
                
            point_name = target_slot["point_name"]
            
            # Send 3 requests quickly
            for u in USERS:
                resp = requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item, "user_id": u, "quantity": 1})
                log(f"Sent drop for {u} -> Status: {resp.json().get('status')}")
                
            # Now process the queue correctly: To process a queue for a full slot, we must pickup!
            for step in range(3):
                delay(2.0)
                if step == 0:
                    log(f"Confirming first drop...")
                    c_resp = requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                    if c_resp.status_code == 200:
                        log("Confirmed first drop. Slot is now FULL. Next drops are in queue waiting.")
                    else:
                        log(f"Confirm failed: {c_resp.text}")
                else:
                    log(f"Picking up item to make room for queued drop {step}...")
                    requests.post(f"{BASE_URL}/slot/pickup", json={"point_name": point_name, "user_id": "TEST_PICKER", "quantity": 1})
                    delay(1.5)
                    log(f"Confirming pickup (this will auto-pop the queue into DROP_RESERVED!)...")
                    requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                    delay(1.5)
                    log(f"Confirming the auto-popped drop {step}...")
                    c_resp = requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                    if c_resp.status_code == 200:
                        log(f"Confirmed queued drop {step}.")
                    else:
                        log(f"Confirm queued drop failed: {c_resp.text}")
                    
        delay(1.0)
        
    log("\nLoop Test Completed!")

if __name__ == "__main__":
    run_loop()
