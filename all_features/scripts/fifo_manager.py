#!/usr/bin/env python3
"""
FIFO Inventory & Storage Slot Management Engine
Class-based WMS Core with State Machine, Sensor Monitoring, Queue Scheduling, and QR Actions.
"""

import os
import csv
import json
import time
import threading
from enum import Enum
from datetime import datetime
from typing import List, Dict, Any, Optional


class SlotState(str, Enum):
    EMPTY = "EMPTY"
    DROP_RESERVED = "DROP_RESERVED"
    FULL = "FULL"
    PICKUP_RESERVED = "PICKUP_RESERVED"


def get_next_state(current: str, event: str) -> str:
    """Pure state machine transition calculator"""
    table = {
        (SlotState.EMPTY, "DROP_REQUEST"): SlotState.DROP_RESERVED,
        (SlotState.DROP_RESERVED, "SENSOR_ON"): SlotState.FULL,
        (SlotState.DROP_RESERVED, "TIMEOUT"): SlotState.EMPTY,
        (SlotState.FULL, "PICKUP_REQUEST"): SlotState.PICKUP_RESERVED,
        (SlotState.PICKUP_RESERVED, "SENSOR_OFF"): SlotState.EMPTY,
        (SlotState.PICKUP_RESERVED, "TIMEOUT"): SlotState.FULL,
    }
    return table.get((current, event), current).value


def now_ts() -> str:
    """Return standard formatted timestamp: DD/MM/YY HH:MM:SS"""
    return datetime.now().astimezone().strftime("%d/%m/%y %H:%M:%S")


def get_default_base_dir() -> str:
    """Resolve project base directory (parent of scripts directory)."""
    curr = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(curr) == "scripts":
        return os.path.dirname(curr)
    return curr


class FIFOManager:
    """Thread-safe FIFO Warehouse Storage Manager and State Controller."""

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or get_default_base_dir()
        self.config_file = os.path.join(self.base_dir, "data/config.json")
        self.history_file = os.path.join(self.base_dir, "data/history.csv")
        self.config_version = 0
        self.lock = threading.Lock()

        # Core in-memory data
        self.config: Dict[str, Any] = {}
        self.slots: List[Dict[str, Any]] = []
        self.users_db: List[Dict[str, Any]] = []
        self.sensor_mapping: Dict[str, str] = {}
        self.latest_sensors_cache: Dict[str, bool] = {}

        # Ensure directories exist
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        self.load_config()

        # Background sensor monitoring thread
        self.running = True
        self.monitor_thread = threading.Thread(target=self._sensor_monitor_loop, daemon=True)
        self.monitor_thread.start()

    # -------------------------------------------------------------------------
    # Configuration & Persistence
    # -------------------------------------------------------------------------

    def load_config(self):
        """Load configuration from config.json into memory."""
        with self.lock:
            if not os.path.exists(self.config_file):
                default_config = {
                    "server": {"host": "0.0.0.0", "port": 8000},
                    "use_sensor": True,
                    "users": [
                        {"user_id": "ROBOT_01", "priority": 1, "role": "Autonomous Lifter"},
                        {"user_id": "operator", "priority": 1, "role": "Warehouse Operator"}
                    ],
                    "storage": {"points": []},
                    "sensor_mapping": {}
                }
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)

            with open(self.config_file, "r", encoding="utf-8") as f:
                self.config = json.load(f)

            self.slots = self.config.get("storage", {}).get("points", [])
            self.users_db = self.config.get("users", [])
            self.sensor_mapping = self.config.get("sensor_mapping", {})
            self.latest_sensors_cache = {s: False for s in self.sensor_mapping.keys()}

    def save_config(self):
        """Atomically persist active configuration to disk."""
        self.config_version += 1
        tmp = self.config_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
        os.replace(tmp, self.config_file)

    def add_history(self, action: str, user_id: str, point: str, item: str, note: str = ""):
        """Append an event transaction record to CSV history log."""
        record_time = now_ts()
        write_header = not os.path.exists(self.history_file) or os.path.getsize(self.history_file) == 0
        with open(self.history_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["action", "user_id", "point_name", "item_type", "time", "note"])
            writer.writerow([action, user_id, point, item, record_time, note])

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent transaction history records in reverse chronological order."""
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                records = reader[-limit:] if limit else reader
                records.reverse()
                return records
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Slot Helpers & Priority Queue
    # -------------------------------------------------------------------------

    def find_slot(self, name: str) -> Optional[Dict[str, Any]]:
        """Case-insensitive slot search by point name."""
        if not name:
            return None
        p = name.strip().lower()
        return next((s for s in self.slots if s.get("point_name", "").strip().lower() == p), None)

    def get_user_priority(self, uid: str) -> int:
        """Get priority level for a specific user ID (default: 999)."""
        return next((u.get("priority", 999) for u in self.users_db if u.get("user_id") == uid), 999)

    def sort_queue(self, q_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort queue entries by user priority (ascending) and request time."""
        return sorted(q_list, key=lambda x: (self.get_user_priority(x.get("user_id")), x.get("request_time", "")))

    def reset_slot_data(self, s: Dict[str, Any]):
        """Clear dynamic contents of a slot back to EMPTY state."""
        s.update({
            "status": SlotState.EMPTY.value,
            "items": [],
            "queue": [],
            "out_time": "",
            "pickup_by": "",
            "last_drop_by": "",
            "last_drop_time": "",
            "reserved_for": "",
            "reserved_item_type": "",
            "reserved_at": ""
        })

    # -------------------------------------------------------------------------
    # Warehouse Business Logic
    # -------------------------------------------------------------------------

    def get_slots_data(self) -> Dict[str, Any]:
        """Return slots snapshot for dashboard UI."""
        with self.lock:
            return {
                "slots": self.slots,
                "users": self.users_db,
                "use_sensor": self.config.get("use_sensor", True),
                "version": self.config_version
            }

    def suggest_slots(self, item_type: str, user_id: str = "") -> List[Dict[str, Any]]:
        """Suggest matching empty storage slots for a specified item type."""
        with self.lock:
            item = item_type.strip()
            if not item:
                raise ValueError("Item type cannot be empty")
            matches = []
            for s in self.slots:
                if not s.get("enabled", True) or s.get("status") != SlotState.EMPTY.value:
                    continue
                allowed = s.get("allowed_item") or []
                if item in allowed:
                    matches.append({"point_name": s["point_name"], "priority": 1, "action_type": "MATCH"})
                elif not allowed or "*" in allowed:
                    matches.append({"point_name": s["point_name"], "priority": 2, "action_type": "ANY"})

            return sorted(matches, key=lambda x: x["priority"])

    def drop_item(self, point_name: str, item_type: str, user_id: str, note: str = "") -> Dict[str, Any]:
        """Reserve or queue a drop operation into a storage slot."""
        with self.lock:
            s = self.find_slot(point_name)
            if not s or not s.get("enabled", True):
                raise ValueError("Invalid or disabled slot")

            allowed = s.get("allowed_item") or []
            if allowed and "*" not in allowed and item_type not in allowed:
                raise ValueError(f"Item '{item_type}' is not allowed in slot '{point_name}'")

            u_p = self.get_user_priority(user_id)
            stat = s.get("status", SlotState.EMPTY.value)

            if stat == SlotState.DROP_RESERVED.value:
                r_u = s.get("reserved_for", "")
                if user_id == r_u:
                    return {"status": "RESERVED", "message": f"Slot {point_name} is already reserved for {user_id}"}
                if u_p >= self.get_user_priority(r_u):
                    s.setdefault("queue", []).append({
                        "item_type": item_type,
                        "user_id": user_id,
                        "request_time": now_ts(),
                        "note": note
                    })
                    s["queue"] = self.sort_queue(s["queue"])
                    self.save_config()
                    return {"status": "QUEUED", "message": f"Slot is busy. Added {user_id} to queue"}
                else:
                    # Preempt lower priority reservation
                    s.setdefault("queue", []).append({
                        "item_type": s.get("reserved_item_type", ""),
                        "user_id": r_u,
                        "request_time": s.get("reserved_at", now_ts()),
                        "note": "preempted"
                    })
                    s["queue"] = self.sort_queue(s["queue"])
                    s.update({
                        "reserved_for": user_id,
                        "reserved_item_type": item_type,
                        "reserved_at": now_ts(),
                        "last_drop_by": user_id,
                        "items": [{
                            "item_type": item_type,
                            "user_id": user_id,
                            "drop_by": user_id,
                            "pickup_by": "",
                            "in_time": now_ts(),
                            "note": note
                        }]
                    })
                    self.add_history("DROP_REQUEST", user_id, point_name, item_type, note)
                    self.save_config()
                    return {"status": "PREEMPTED", "message": f"Preempted reservation for {user_id}"}

            elif stat in [SlotState.FULL.value, SlotState.PICKUP_RESERVED.value]:
                if any(q.get("user_id") == user_id for q in s.get("queue", [])):
                    raise ValueError(f"User {user_id} is already in queue for slot {point_name}")
                s.setdefault("queue", []).append({
                    "item_type": item_type,
                    "user_id": user_id,
                    "request_time": now_ts(),
                    "note": note
                })
                s["queue"] = self.sort_queue(s["queue"])
                self.save_config()
                return {"status": "QUEUED", "message": f"Slot {point_name} is full. Queued {user_id}"}

            elif stat == SlotState.EMPTY.value:
                s.update({
                    "status": SlotState.DROP_RESERVED.value,
                    "reserved_for": user_id,
                    "reserved_item_type": item_type,
                    "reserved_at": now_ts(),
                    "last_drop_by": user_id,
                    "items": [{
                        "item_type": item_type,
                        "user_id": user_id,
                        "drop_by": user_id,
                        "pickup_by": "",
                        "in_time": now_ts(),
                        "note": note
                    }]
                })
                self.add_history("DROP_REQUEST", user_id, point_name, item_type, note)
                self.save_config()
                return {"status": "RESERVED", "message": f"Successfully reserved slot {point_name} for {user_id}"}

            raise ValueError(f"Unknown slot status: {stat}")

    def pickup_item(self, item_type: str, user_id: str) -> Dict[str, Any]:
        """Dispatch oldest item of requested type in FIFO order."""
        with self.lock:
            candidates = [
                s for s in self.slots
                if s.get("enabled", True)
                and s.get("status") == SlotState.FULL.value
                and s.get("items")
                and s["items"][0].get("item_type") == item_type
            ]
            if not candidates:
                raise KeyError(f"No stock found for item type '{item_type}'")

            target_slot = sorted(candidates, key=lambda x: x["items"][0].get("in_time", ""))[0]
            target_slot.update({
                "status": SlotState.PICKUP_RESERVED.value,
                "pickup_by": user_id,
                "out_time": now_ts()
            })
            dispatched_item = target_slot["items"][0] if target_slot.get("items") else {}
            self.add_history("PICKUP_REQUEST", user_id, target_slot["point_name"], item_type)
            self.save_config()
            return {
                "status": "PICKUP_RESERVED",
                "target_slot": target_slot["point_name"],
                "dispatched_item": dispatched_item
            }

    def reset_slot(self, point_name: str):
        """Reset a slot manually."""
        with self.lock:
            s = self.find_slot(point_name)
            if s:
                self.reset_slot_data(s)
                self.save_config()

    def confirm_slot(self, point_name: str) -> Dict[str, Any]:
        """Confirm a DROP_RESERVED or PICKUP_RESERVED transaction in manual mode."""
        with self.lock:
            slot = self.find_slot(point_name)
            if not slot:
                raise ValueError("Invalid slot")

            stat = slot.get("status", "").strip().upper()
            if stat not in [SlotState.DROP_RESERVED.value, SlotState.PICKUP_RESERVED.value]:
                raise ValueError(f"Slot is in status {stat}, cannot confirm.")

            last_action, last_user, last_item, last_note = None, "", "", ""

            if os.path.exists(self.history_file):
                try:
                    with open(self.history_file, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for record in reader:
                            if record.get("point_name") == slot["point_name"]:
                                last_action = record.get("action")
                                last_user = record.get("user_id", "")
                                last_item = record.get("item_type", "")
                                last_note = record.get("note", "")
                except Exception as e:
                    raise RuntimeError(f"Error reading history log: {e}")

            if not last_action:
                raise ValueError("No history log found for this slot.")

            if stat == SlotState.DROP_RESERVED.value:
                if last_action != "DROP_REQUEST":
                    raise ValueError(f"Last log action was {last_action}, expected DROP_REQUEST.")

                slot["status"] = SlotState.FULL.value
                if slot.get("items"):
                    slot["items"][0]["in_time"] = now_ts()
                self.add_history("DROP_COMPLETE", last_user, slot["point_name"], last_item, last_note)
                self.save_config()
                return {"status": "OK", "message": f"Drop confirmed for slot {slot['point_name']}"}

            elif stat == SlotState.PICKUP_RESERVED.value:
                if last_action != "PICKUP_REQUEST":
                    raise ValueError(f"Last log action was {last_action}, expected PICKUP_REQUEST.")

                slot["status"] = SlotState.EMPTY.value
                self.add_history("PICKUP_COMPLETE", last_user, slot["point_name"], last_item, last_note)
                q = slot.get("queue", [])
                if q:
                    nxt = q.pop(0)
                    slot.update({
                        "status": SlotState.DROP_RESERVED.value,
                        "reserved_for": nxt["user_id"],
                        "reserved_item_type": nxt["item_type"],
                        "reserved_at": now_ts(),
                        "last_drop_by": nxt["user_id"],
                        "items": [{
                            "item_type": nxt["item_type"],
                            "user_id": nxt["user_id"],
                            "drop_by": nxt["user_id"],
                            "pickup_by": "",
                            "in_time": now_ts(),
                            "note": nxt.get("note", "")
                        }]
                    })
                    self.add_history("DROP_REQUEST", nxt["user_id"], slot["point_name"], nxt["item_type"], nxt.get("note", ""))
                else:
                    self.reset_slot_data(slot)
                slot["queue"] = q
                self.save_config()
                return {"status": "OK", "message": f"Pickup confirmed for slot {slot['point_name']}"}

            raise ValueError(f"Unexpected status: {stat}")

    def update_users(self, new_users: List[Dict[str, Any]]):
        """Update operator profiles."""
        with self.lock:
            user_map = {u["user_id"]: u for u in self.config.get("users", [])}
            for nu in new_users:
                uid = nu.get("user_id")
                if uid:
                    if uid in user_map:
                        user_map[uid].update(nu)
                    else:
                        user_map[uid] = nu
            self.config["users"] = list(user_map.values())
            self.users_db = self.config["users"]
            self.save_config()

    def update_config(self, payload: Dict[str, Any]):
        """Update system configurations, slots, and sensor mappings."""
        with self.lock:
            self.config["users"] = payload.get("users", [])
            new_slots = payload.get("slots", [])
            self.config["storage"]["points"] = new_slots
            self.config["use_sensor"] = payload.get("use_sensor", True)

            if "sensor_mapping" not in self.config:
                self.config["sensor_mapping"] = {}

            current_mapped_slots = set(self.config["sensor_mapping"].values())
            for slot in new_slots:
                name = slot.get("point_name")
                if name and name not in current_mapped_slots:
                    digits = "".join(filter(str.isdigit, name))
                    sensor_id = f"S{int(digits)}" if digits else f"S_{name}"
                    while sensor_id in self.config["sensor_mapping"]:
                        sensor_id += "_"
                    self.config["sensor_mapping"][sensor_id] = name

            self.users_db = self.config["users"]
            self.slots = self.config["storage"]["points"]
            self.sensor_mapping = self.config.get("sensor_mapping", {})

            for sid in self.sensor_mapping.keys():
                if sid not in self.latest_sensors_cache:
                    self.latest_sensors_cache[sid] = False

            self.save_config()

    # -------------------------------------------------------------------------
    # Sensor State & Background Monitor Loop
    # -------------------------------------------------------------------------

    def set_sensor_state(self, sensor_id: str, detected: bool):
        """Update optical sensor state."""
        with self.lock:
            self.latest_sensors_cache[sensor_id] = detected

    def get_sensors_status(self) -> Dict[str, bool]:
        """Get snapshot of latest sensor states."""
        with self.lock:
            return dict(self.latest_sensors_cache)

    def _sensor_monitor_loop(self):
        """Continuous background hardware sensor polling thread."""
        while self.running:
            try:
                with self.lock:
                    if self.config.get("use_sensor", True):
                        for sid, sname in self.sensor_mapping.items():
                            on = self.latest_sensors_cache.get(sid, False)
                            slot = self.find_slot(sname)
                            if not slot:
                                continue
                            stat = slot.get("status", "").strip().upper()

                            if stat == SlotState.DROP_RESERVED.value and on:
                                slot["status"] = get_next_state(stat, "SENSOR_ON")
                                if slot.get("items"):
                                    slot["items"][0]["in_time"] = now_ts()
                                self.add_history("DROP_COMPLETE", slot.get("last_drop_by", ""), slot["point_name"], slot.get("reserved_item_type", ""))
                                self.save_config()

                            elif stat == SlotState.PICKUP_RESERVED.value and not on:
                                slot["status"] = get_next_state(stat, "SENSOR_OFF")
                                self.add_history("PICKUP_COMPLETE", slot.get("pickup_by", ""), slot["point_name"], "")
                                q = slot.get("queue", [])
                                if q:
                                    nxt = q.pop(0)
                                    slot.update({
                                        "status": SlotState.DROP_RESERVED.value,
                                        "reserved_for": nxt["user_id"],
                                        "reserved_item_type": nxt["item_type"],
                                        "reserved_at": now_ts(),
                                        "last_drop_by": nxt["user_id"],
                                        "items": [{
                                            "item_type": nxt["item_type"],
                                            "user_id": nxt["user_id"],
                                            "drop_by": nxt["user_id"],
                                            "pickup_by": "",
                                            "in_time": now_ts(),
                                            "note": nxt.get("note", "")
                                        }]
                                    })
                                    self.add_history("DROP_REQUEST", nxt["user_id"], slot["point_name"], nxt["item_type"], nxt.get("note", ""))
                                else:
                                    self.reset_slot_data(slot)
                                slot["queue"] = q
                                self.save_config()
            except Exception as e:
                pass
            time.sleep(0.2)

    # -------------------------------------------------------------------------
    # QR Code Payload Parser
    # -------------------------------------------------------------------------

    @staticmethod
    def parse_qr_payload(raw_text: str) -> Dict[str, Any]:
        """Parse QR string whether JSON formatted or plain text."""
        raw_text = raw_text.strip()
        if raw_text.startswith("{") and raw_text.endswith("}"):
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    return {
                        "raw": raw_text,
                        "item_type": parsed.get("item_type") or parsed.get("item") or "",
                        "point_name": parsed.get("point_name") or parsed.get("slot") or parsed.get("point") or "",
                        "user_id": parsed.get("user_id") or parsed.get("user") or "",
                        "note": parsed.get("note") or "",
                        "action": parsed.get("action") or "",
                    }
            except Exception:
                pass
        return {
            "raw": raw_text,
            "item_type": raw_text,
            "point_name": "",
            "user_id": "",
            "note": "",
            "action": "",
        }


# Class aliases for flexible importing
FIFO = FIFOManager
FIFOService = FIFOManager

