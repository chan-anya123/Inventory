import os, json, threading, time, uvicorn, csv, io
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from collections import deque
from enum import Enum

# --- CONFIG & ENUMS ---
class SlotState(str, Enum):
    EMPTY = "EMPTY"
    DROP_RESERVED = "DROP_RESERVED"
    FULL = "FULL"
    PICKUP_RESERVED = "PICKUP_RESERVED"

# --- REQUEST PAYLOAD TYPES (Using Dict Validation) ---

# --- UTILS & LOGIC FUNCTIONS ---
def get_next_state(current: str, event: str) -> str:
    """Pure function to calculate next state"""
    table = {
        (SlotState.EMPTY, "DROP_REQUEST"): SlotState.DROP_RESERVED,
        (SlotState.DROP_RESERVED, "SENSOR_ON"): SlotState.FULL,
        (SlotState.DROP_RESERVED, "TIMEOUT"): SlotState.EMPTY,
        (SlotState.FULL, "PICKUP_REQUEST"): SlotState.PICKUP_RESERVED,
        (SlotState.PICKUP_RESERVED, "SENSOR_OFF"): SlotState.EMPTY,
        (SlotState.PICKUP_RESERVED, "TIMEOUT"): SlotState.FULL,
    }
    return table.get((current, event), current).value

def now_ts(): return datetime.now().astimezone().strftime("%d/%m/%y %H:%M:%S")

def find_slot(name: str):
    p = name.strip().lower()
    return next((s for s in slots if s["point_name"].strip().lower() == p), None)

def save_config():
    global CONFIG_VERSION
    CONFIG_VERSION += 1
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(config, f, indent=4, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)

def get_user_priority(uid):
    return next((u.get("priority", 999) for u in users_db if u["user_id"] == uid), 999)

def sort_queue(q_list):
    return sorted(q_list, key=lambda x: (get_user_priority(x["user_id"]), x.get("request_time", "")))

def reset_slot_data(s):
    s.update({"items": [], "queue": [], "out_time": "", "pickup_by": "", 
              "last_drop_by": "", "last_drop_time": "", "reserved_for": "", "reserved_item_type": "", "reserved_at": ""})

# --- INITIALIZATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "data/config.json")
HISTORY_FILE = os.path.join(BASE_DIR, "data/history.csv")
CONFIG_VERSION = 0

def add_history(action, user_id, point, item, note=""):
    record_time = now_ts()
    write_header = not os.path.exists(HISTORY_FILE) or os.path.getsize(HISTORY_FILE) == 0
    with open(HISTORY_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["action", "user_id", "point_name", "item_type", "time", "note"])
        writer.writerow([action, user_id, point, item, record_time, note])

with open(CONFIG_FILE, "r", encoding="utf-8") as f: config = json.load(f)

# --- MIGRATION: unit_type -> storage_type ---
migrated = False
if "unit_types" in config and "storage_types" not in config:
    config["storage_types"] = config.pop("unit_types")
    migrated = True
for slot in config.get("storage", {}).get("points", []):
    if "unit_type" in slot:
        slot["storage_type"] = slot.pop("unit_type")
        migrated = True
if migrated:
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(config, f, indent=4, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)

slots, users_db, sensor_mapping = config["storage"]["points"], config["users"], config.get("sensor_mapping", {})
latest_sensors_cache = {s: False for s in sensor_mapping.keys()}
lock = threading.Lock()

app = FastAPI(title="WMS System")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# --- BACKGROUND MONITOR ---
def sensor_monitor():
    while True:
        try:
            with lock:
                if config.get("use_sensor", True):
                    for sid, sname in sensor_mapping.items():
                        on, slot = latest_sensors_cache.get(sid, False), find_slot(sname)
                        if not slot: continue
                        stat = slot.get("status", "").strip().upper()

                        if stat == SlotState.DROP_RESERVED.value and on:
                            slot["status"] = get_next_state(stat, "SENSOR_ON")
                            if slot.get("items"): slot["items"][0]["in_time"] = now_ts()
                            add_history("DROP_COMPLETE", slot.get("last_drop_by",""), slot["point_name"], slot.get("reserved_item_type",""))
                            save_config()

                        elif stat == SlotState.PICKUP_RESERVED.value and not on:
                            slot["status"] = get_next_state(stat, "SENSOR_OFF")
                            add_history("PICKUP_COMPLETE", slot.get("pickup_by",""), slot["point_name"], "")
                            q = slot.get("queue", [])
                            if q:
                                nxt = q.pop(0)
                                slot.update({"status": SlotState.DROP_RESERVED.value, "reserved_for": nxt["user_id"],
                                             "reserved_item_type": nxt["item_type"], "reserved_at": now_ts(), "last_drop_by": nxt["user_id"],
                                             "items": [{"item_type": nxt["item_type"], "user_id": nxt["user_id"], "drop_by": nxt["user_id"], 
                                                       "pickup_by": "", "in_time": now_ts(), "note": nxt.get("note", "")}]})
                                add_history("DROP_REQUEST", nxt["user_id"], slot["point_name"], nxt["item_type"], nxt.get("note", ""))
                            else:
                                reset_slot_data(slot)
                                slot["status"] = SlotState.EMPTY.value
                            slot["queue"] = q
                            save_config()
        except Exception as e: print(f"Monitor Error: {e}")
        time.sleep(0.2)

threading.Thread(target=sensor_monitor, daemon=True).start()

def run_manual_server():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8081))
        s.close()
    except OSError:
        return
    try:
        import uvicorn, sys
        if BASE_DIR not in sys.path:
            sys.path.append(BASE_DIR)
        import manual
        uvicorn.run(manual.app, host="0.0.0.0", port=8081, log_level="warning")
    except Exception as e:
        print(f"Failed to start manual server: {e}")

if os.environ.get("DISABLE_MANUAL_SERVER") != "true":
    threading.Thread(target=run_manual_server, daemon=True).start()

# --- ROUTES ---
@app.get("/")
def index(): return FileResponse(os.path.join(BASE_DIR, "vue.html"))

from fastapi.responses import PlainTextResponse

@app.get("/api/manual", response_class=PlainTextResponse)
def get_manual():
    readme_path = os.path.join(os.path.dirname(BASE_DIR), "README.md")
    if not os.path.exists(readme_path):
        raise HTTPException(404, "README.md not found")
    with open(readme_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/slots")
def get_slots(): return {"slots": slots, "users": users_db, "use_sensor": config.get("use_sensor", True),
        "pickup_strategy": config.get("pickup_strategy", "FIFO"),
        "storage_types": config.get("storage_types", []),
        "item_types": config.get("item_types", [{"name": "*"}, {"name": "cookie"}]),
        "sensor_mapping": config.get("sensor_mapping", {}),
        "map_layout": config.get("map_layout", {}),
        "map_size": config.get("map_size", {"width": 10, "height": 10}),
        "version": CONFIG_VERSION}

@app.post("/slot/suggest")
def suggest(req: dict):
    with lock:
        item = req.get("item_type", "").strip()
        if not item: raise HTTPException(400, "Item empty")
        storage_types_map = {u["name"]: u.get("strategy", "FIFO") for u in config.get("storage_types", [])}
        
        candidates = []
        for s in slots:
            if not s.get("enabled", True) or s.get("status") != SlotState.EMPTY.value: continue
            a = s.get("allowed_item") or []
            if item in a: candidates.append((s, 1, "MATCH"))
            elif not a or "*" in a: candidates.append((s, 2, "ANY"))
            
        grouped = {}
        for s, prio, act in candidates:
            p_node = s.get("parent_node") or s["point_name"].split(':')[0]
            grouped.setdefault(p_node, []).append((s, prio, act))
            
        m = []
        for p_node, group in grouped.items():
            if not group: continue
            u_type = group[0][0].get("storage_type", "")
            strat = storage_types_map.get(u_type, "FIFO")
            
            if strat == "LIFO":
                # Only keep the lowest level index for LIFO nodes
                group.sort(key=lambda x: x[0].get("level_index", 0))
                m.append({"point_name": group[0][0]["point_name"], "priority": group[0][1], "action_type": group[0][2]})
            else:
                for s, prio, act in group:
                    m.append({"point_name": s["point_name"], "priority": prio, "action_type": act})
                    
        if not m: raise HTTPException(404, "No slots")
        return {"slots": sorted(m, key=lambda x: (x["priority"], x["point_name"]))}

@app.post("/slot/drop")
def drop(req: dict):
    with lock:
        point_name = req.get("point_name")
        item_type = req.get("item_type")
        user_id = req.get("user_id")
        note = req.get("note", "")
        
        s = find_slot(point_name)
        if not s or not s.get("enabled", True): raise HTTPException(400, "Invalid slot")
        a = s.get("allowed_item") or []
        if a and "*" not in a and item_type not in a: raise HTTPException(400, "Item not allowed")
        u_p, stat = get_user_priority(user_id), s["status"]
 
        if stat == SlotState.DROP_RESERVED.value:
            r_u = s.get("reserved_for", "")
            if user_id == r_u: return {"status": "RESERVED", "message": "Already held"}
            if u_p >= get_user_priority(r_u):
                s.setdefault("queue", []).append({"item_type": item_type, "user_id": user_id, "request_time": now_ts(), "note": note})
                s["queue"] = sort_queue(s["queue"]); save_config(); return {"status": "QUEUED"}
            else:
                s.setdefault("queue", []).append({"item_type": s["reserved_item_type"], "user_id": r_u, "request_time": s["reserved_at"], "note": "preempted"})
                s["queue"] = sort_queue(s["queue"])
                s.update({
                    "reserved_for": user_id,
                    "reserved_item_type": item_type,
                    "reserved_at": now_ts(),
                    "last_drop_by": user_id,
                    "items": [{"item_type": item_type, "user_id": user_id, "drop_by": user_id, "pickup_by": "", "in_time": now_ts(), "note": note}]
                })
                add_history("DROP_REQUEST", user_id, point_name, item_type, note)
                save_config()
                return {"status": "PREEMPTED"}
        elif stat in [SlotState.FULL.value, SlotState.PICKUP_RESERVED.value]:
            if any(q["user_id"] == user_id for q in s.get("queue", [])): raise HTTPException(400, "Already queued")
            s.setdefault("queue", []).append({"item_type": item_type, "user_id": user_id, "request_time": now_ts(), "note": note})
            s["queue"] = sort_queue(s["queue"]); save_config(); return {"status": "QUEUED"}
        elif stat == SlotState.EMPTY.value:
            s.update({"status": SlotState.DROP_RESERVED.value, "reserved_for": user_id, "reserved_item_type": item_type, "reserved_at": now_ts(), "last_drop_by": user_id,
                      "items": [{"item_type": item_type, "user_id": user_id, "drop_by": user_id, "pickup_by": "", "in_time": now_ts(), "note": note}]})
            add_history("DROP_REQUEST", user_id, point_name, item_type, note); save_config(); return {"status": "RESERVED"}

@app.post("/slot/pickup")
def pickup_slot(req: dict):
    with lock:
        point_name = req.get("point_name")
        user_id = req.get("user_id")
        
        t = find_slot(point_name)
        if not t or t["status"] != SlotState.FULL.value:
            raise HTTPException(404, "Target level is empty or invalid")
            
        t.update({"status": SlotState.PICKUP_RESERVED.value, "pickup_by": user_id, "out_time": now_ts()})
        dispatched_item = t["items"][0] if t.get("items") else {}
        add_history("PICKUP_REQUEST", user_id, t["point_name"], dispatched_item.get("item_type", ""))
        save_config()
        return {"status": "PICKUP_RESERVED", "target_slot": t["point_name"], "dispatched_item": dispatched_item}

@app.post("/slot/cancel")
def cancel_task(req: dict):
    with lock:
        s = find_slot(req.get("point_name"))
        if not s: raise HTTPException(400, "Invalid slot")
        
        stat = s.get("status")
        
        # Reset task specific data
        s.update({
            "queue": [],
            "pickup_by": "",
            "out_time": "",
            "reserved_for": "",
            "reserved_item_type": "",
            "reserved_at": ""
        })
        
        # In Manual Mode:
        # If cancelling a DROP, the item wasn't actually placed yet, so we must remove it.
        # If cancelling a PICKUP, the item is still there, so we keep it.
        if not config.get("use_sensor", True):
            if stat == SlotState.DROP_RESERVED.value:
                s["status"] = SlotState.EMPTY.value
                s["items"] = []
            elif stat == SlotState.PICKUP_RESERVED.value:
                s["status"] = SlotState.FULL.value
            # If it's already EMPTY or FULL, we don't touch the status.
        else:
            # In Auto Mode:
            # Status always follows the sensor
            sensor_id = None
            for sid, target in config.get("sensor_mapping", {}).items():
                if target == s["point_name"]:
                    sensor_id = sid
                    break
            
            is_on = latest_sensors_cache.get(sensor_id, False) if sensor_id else False
            if is_on:
                s["status"] = SlotState.FULL.value
            else:
                s["status"] = SlotState.EMPTY.value
                s["items"] = []
                
        save_config()
        return {"message": "Cancelled and reset successfully"}

@app.post("/slot/reset")
def reset(req: dict):
    with lock:
        s = find_slot(req.get("point_name"))
        if s:
            reset_slot_data(s)
            if config.get("use_sensor", True):
                sid = next((k for k, v in sensor_mapping.items() if v == s["point_name"]), None)
                if sid:
                    s["status"] = SlotState.FULL.value if latest_sensors_cache.get(sid, False) else SlotState.EMPTY.value
                else:
                    s["status"] = SlotState.EMPTY.value
            else:
                requested = req.get("status", "").strip().upper()
                s["status"] = requested if requested in [SlotState.EMPTY.value, SlotState.FULL.value] else SlotState.EMPTY.value
            save_config()
        return {"message": "Reset"}

@app.post("/slot/confirm")
def confirm(req: dict):
    with lock:
        if config.get("use_sensor", True):
            raise HTTPException(400, "Cannot manually confirm while in Auto Mode (Sensors Enabled). Please use physical sensors.")
            
        point_name = req.get("point_name")
        slot = find_slot(point_name)
        if not slot: raise HTTPException(400, "Invalid slot")
        
        stat = slot.get("status", "").strip().upper()
        if stat not in [SlotState.DROP_RESERVED.value, SlotState.PICKUP_RESERVED.value]:
            raise HTTPException(400, f"Slot is in status {stat}, cannot confirm.")

        last_action = None
        last_user = ""
        last_item = ""
        last_note = ""
        
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for record in reader:
                        if record.get("point_name") == slot["point_name"]:
                            last_action = record.get("action")
                            last_user = record.get("user_id", "")
                            last_item = record.get("item_type", "")
                            last_note = record.get("note", "")
            except Exception as e:
                raise HTTPException(500, f"Error reading log: {e}")

        if not last_action:
            raise HTTPException(400, "No history log found for this slot.")

        if stat == SlotState.DROP_RESERVED.value:
            if last_action != "DROP_REQUEST":
                raise HTTPException(400, f"Last log action was {last_action}, expected DROP_REQUEST.")
            
            slot["status"] = SlotState.FULL.value
            if slot.get("items"):
                slot["items"][0]["in_time"] = now_ts()
            add_history("DROP_COMPLETE", last_user, slot["point_name"], last_item, last_note)
            save_config()
            return {"status": "OK", "message": f"Drop confirmed for slot {slot['point_name']}"}

        elif stat == SlotState.PICKUP_RESERVED.value:
            if last_action != "PICKUP_REQUEST":
                raise HTTPException(400, f"Last log action was {last_action}, expected PICKUP_REQUEST.")
            
            slot["status"] = SlotState.EMPTY.value
            add_history("PICKUP_COMPLETE", last_user, slot["point_name"], last_item, last_note)
            q = slot.get("queue", [])
            if q:
                nxt = q.pop(0)
                slot.update({"status": SlotState.DROP_RESERVED.value, "reserved_for": nxt["user_id"],
                             "reserved_item_type": nxt["item_type"], "reserved_at": now_ts(), "last_drop_by": nxt["user_id"],
                             "items": [{"item_type": nxt["item_type"], "user_id": nxt["user_id"], "drop_by": nxt["user_id"], 
                                       "pickup_by": "", "in_time": now_ts(), "note": nxt.get("note", "")}]})
                add_history("DROP_REQUEST", nxt["user_id"], slot["point_name"], nxt["item_type"], nxt.get("note", ""))
            else:
                reset_slot_data(slot)
            slot["queue"] = q
            save_config()
            return {"status": "OK", "message": f"Pickup confirmed for slot {slot['point_name']}"}

@app.post("/config/update/users")
def update_users(payload: dict):
    global users_db
    with lock:
        # Create a mapping of existing users for easy merging
        user_map = {u["user_id"]: u for u in config["users"]}
        for new_user in payload.get("users", []):
            uid = new_user.get("user_id")
            if uid:
                if uid in user_map:
                    user_map[uid].update(new_user)
                else:
                    user_map[uid] = new_user
        
        config["users"] = list(user_map.values())
        users_db = config["users"]
        save_config()
        return {"status": "OK"}

@app.post("/config/update")
def update_c(payload: dict):
    global users_db, slots, sensor_mapping, latest_sensors_cache
    with lock:
        config["users"] = payload.get("users", [])
        new_slots = payload.get("slots", [])
        
        old_slots_map = {s["point_name"].strip().lower(): s for s in slots}
        processed_slots = []
        
        for slot in new_slots:
            name = slot.get("point_name", "").strip()
            if not name: continue
            
            old_s = old_slots_map.get(name.lower())
            if old_s:
                slot["items"] = old_s.get("items", [])
                slot["queue"] = old_s.get("queue", [])
                slot["status"] = old_s.get("status", "EMPTY")
                
                for k in ["last_drop_by", "last_drop_time", "pickup_by", "out_time", "reserved_for", "reserved_item_type", "reserved_quantity", "reserved_at", "pending_drop", "pending_pickup_item"]:
                    if k in old_s:
                        slot[k] = old_s[k]
            else:
                slot.setdefault("items", [])
                slot.setdefault("queue", [])
                slot.setdefault("status", "EMPTY")
            slot["strategy"] = slot.get("strategy", "FIFO")
            
            slot["enabled"] = slot.get("enabled", True)
            slot["max_capacity"] = max(1, int(slot.get("max_capacity", 1)))
            processed_slots.append(slot)
            
        config["storage"]["points"] = processed_slots
        config["use_sensor"] = payload.get("use_sensor", True)
        config["pickup_strategy"] = payload.get("pickup_strategy", "FIFO")
        config["storage_types"] = payload.get("storage_types", [])
        config["item_types"] = payload.get("item_types", [])
        if "map_layout" in payload:
            config["map_layout"] = payload.get("map_layout", {})
        if "map_size" in payload:
            config["map_size"] = payload.get("map_size", {"width": 10, "height": 10})
        
        if "sensor_mapping" not in config:
            config["sensor_mapping"] = {}
            
        current_mapped_targets = set(config["sensor_mapping"].values())
        for slot in processed_slots:
            name = slot.get("point_name")
            if not name: continue
            levels = slot.get("levels", [])
            if not levels: levels = [{"level_name": "Level 1"}]
            
            for i, lvl in enumerate(levels):
                target = f"{name}:{lvl.get('level_name', f'Level {i+1}')}"
                if target not in current_mapped_targets:
                    sensor_id = f"S_{name}_{i+1}"
                    while sensor_id in config["sensor_mapping"]:
                        sensor_id += "_"
                    config["sensor_mapping"][sensor_id] = target
                
        users_db = config["users"]
        slots = config["storage"]["points"]
        sensor_mapping = config.get("sensor_mapping", {})
        
        for sid in sensor_mapping.keys():
            if sid not in latest_sensors_cache:
                latest_sensors_cache[sid] = False
                
        save_config()

@app.post("/config/mode")
def update_mode(req: dict):
    with lock:
        if "use_sensor" in req:
            config["use_sensor"] = bool(req["use_sensor"])
            save_config()
            return {"message": f"Mode updated to {'Auto (Sensor)' if config['use_sensor'] else 'Manual'}"}
        raise HTTPException(400, "Missing 'use_sensor' boolean in payload")

@app.post("/config/map")
def update_map(payload: dict):
    with lock:
        config["map_layout"] = payload.get("map_layout", {})
        config["map_size"] = payload.get("map_size", {"width": 10, "height": 10})
        save_config()
        return {"status": "OK", "version": CONFIG_VERSION}

@app.get("/history")
def get_h(limit: int = 100):
    if not os.path.exists(HISTORY_FILE): return {"history": []}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            records = reader[-limit:] if limit else reader
            records.reverse()
            return {"history": records}
    except: return {"history": []}

@app.post("/sensor/state")
def receive_s(data: dict):
    with lock: latest_sensors_cache[data.get("sensor_id")] = data.get("detected")
    return {"status": "ok", "timestamp": now_ts()}

@app.get("/sensor/status")
def sensor_s():
    with lock: return latest_sensors_cache


@app.post("/slot/manual-status")
def manual_status(req: dict):
    with lock:
        point_name = req.get("point_name", "").strip()
        status = req.get("status", "").strip().upper()

        slot = find_slot(point_name)
        if not slot:
            raise HTTPException(404, "Slot not found")

        valid_status = ["EMPTY", "PARTIAL", "DROP_RESERVED", "FULL", "PICKUP_RESERVED"]
        if status not in valid_status:
            raise HTTPException(400, f"Invalid status. Allowed: {valid_status}")

        old_status = slot.get("status", "")
        reset_slot_data(slot)
        slot["status"] = status
        add_history("MANUAL_STATUS", "manual", point_name, "", f"{old_status} -> {status}")
        save_config()
        return {"status": "OK", "point_name": point_name, "old_status": old_status, "new_status": status}

if __name__ == "__main__": 
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)