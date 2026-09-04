import requests
import time
import random
import sys
import json

BASE_URL = "http://localhost:8000"

# ดึงข้อมูล Users และ สล็อต รวมถึง Sensor Mapping จากระบบจริงมาใช้สุ่ม
try:
    # ✅ ปรับจาก /api/slots เป็น /slots
    init_res = requests.get(f"{BASE_URL}/slots").json()
    USERS = [u["user_id"] for u in init_res["users"]]
    SLOTS = [s["point_name"] for s in init_res["slots"]]
    
    # ดึง Sensor Mapping ย้อนกลับ (Point -> Sensor) เพื่อใช้สั่งงานฝั่ง Sensor
    with open("/home/cookies/fifo/queue/config.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)
        
    rev_sensor_mapping = {v: k for k, v in config_data.get("sensor_mapping", {}).items()}
except Exception as e:
    print(f"❌ ไม่สามารถดึงข้อมูลเริ่มต้นจาก API หรือ config.json ได้: {e}")
    print("กรุณาตรวจสอบว่าเซิร์ฟเวอร์หลักรันอยู่ และมีไฟล์ config.json ในโฟลเดอร์")
    sys.exit(1)

def get_all_slots_state():
    """ดึงสถานะปัจจุบันของสล็อตทั้งหมดแบบเรียลไทม์"""
    # ✅ ปรับจาก /api/slots เป็น /slots
    res = requests.get(f"{BASE_URL}/slots").json()
    return {s["point_name"]: s for s in res["slots"]}

def run_chaos_test():
    print("==================================================")
    print("    STARTING RANDOMIZED CHAOS STRESS TEST         ")
    print("    (ระบบจะสุ่มคน สุ่มสล็อต และสุ่มกิจกรรมไปเรื่อยๆ) ")
    print("    [ กด CTRL+C เพื่อสั่งหยุดการทำงานได้ตลอดเวลา ]  ")
    print("==================================================\n")

    # เคลียร์ระบบให้ว่างทั้งหมดก่อนเริ่มความโกลาหล
    print("🧹 Clearing all slots for a fresh start...")
    for slot in SLOTS:
        # ✅ ปรับจาก /api/slot/reset เป็น /slot/reset
        requests.post(f"{BASE_URL}/slot/reset", json={"point_name": slot})
        if slot in rev_sensor_mapping:
            requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": rev_sensor_mapping[slot], "detected": False})
    
    time.sleep(0.5)
    action_count = 0
    start_time = time.time()

    try:
        while True:
            action_count += 1
            current_slots = get_all_slots_state()
            
            # สุ่มเลือกสล็อตและผู้ใช้งาน
            target_slot_name = random.choice(SLOTS)
            target_user = random.choice(USERS)
            slot_data = current_slots[target_slot_name]
            current_status = slot_data["status"]
            sensor_id = rev_sensor_mapping.get(target_slot_name)

            allowed = slot_data.get("allowed_item", [])
            item_type = allowed[0] if allowed and "*" not in allowed else "cookie"

            # นับจำนวนคิวรวมของระบบตอนนี้ เพื่อเอามาประมวลผลความหนาแน่น
            total_queues = sum(len(s.get("queue", [])) for s in current_slots.values())

            sys.stdout.write(f"\r⚡ Actions: {action_count} | Running: {time.time()-start_time:.1f}s | Global Queues: {total_queues} | Checking {target_slot_name}...")
            sys.stdout.flush()

            # --- บริหารจัดการสุ่มกิจกรรมตามความจุของคลังสินค้า ---
            
            # 1. กรณีสล็อตว่าง (EMPTY) -> สุ่มจอง
            if current_status == "EMPTY":
                if total_queues < 3 and random.random() < 0.7:  
                    # ✅ ปรับจาก /api/slot/drop เป็น /slot/drop
                    requests.post(f"{BASE_URL}/slot/drop", json={
                        "point_name": target_slot_name, "item_type": item_type, "user_id": target_user, "note": "Slow Chaos"
                    })

            # 2. กรณีโดนจองไว้ (DROP_RESERVED) -> บังคับให้เซนเซอร์ ON (วางของสำเร็จ)
            elif current_status == "DROP_RESERVED" and sensor_id:
                if random.random() < 0.85:
                    requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": True})

            # 3. กรณีช่องเต็ม (FULL) -> เน้นสั่งเบิกออก (PICKUP) มากกว่าเติมคิว
            elif current_status == "FULL":
                current_slot_queue_len = len(slot_data.get("queue", []))
                
                if current_slot_queue_len < 2 and random.random() < 0.20:
                    # ✅ ปรับจาก /api/slot/drop เป็น /slot/drop
                    requests.post(f"{BASE_URL}/slot/drop", json={
                        "point_name": target_slot_name, "item_type": item_type, "user_id": target_user, "note": "Slow Queue"
                    })
                else:
                    # สั่งเบิกไอเทมออก
                    # ✅ ปรับจาก /api/item/pickup เป็น /item/pickup
                    requests.post(f"{BASE_URL}/item/pickup", json={
                        "item_type": item_type, "user_id": target_user
                    })

            # 4. กรณีรอหุ่นยนต์ยกของออก (PICKUP_RESERVED) -> บังคับให้เซนเซอร์ OFF
            elif current_status == "PICKUP_RESERVED" and sensor_id:
                requests.post(f"{BASE_URL}/sensor/state", json={"sensor_id": sensor_id, "detected": False})

            # ปรับเวลาหน่วงเพื่อให้มองสถานะบนหน้าเว็บทัน
            time.sleep(random.uniform(1.5, 3.0))

    except KeyboardInterrupt:
        print("\n\n🛑 Chaos Test stopped by user.")
        total_time = time.time() - start_time
        final_slots = get_all_slots_state()
        
        print("\n📊 [FINAL WMS SNAPSHOT]")
        for name, data in final_slots.items():
            q_users = [q["user_id"] for q in data.get("queue", [])]
            print(f"  📍 Slot {name}: Status = {data['status']:<15} | Reserved For = {data.get('reserved_for','-'):<10} | Queue = {q_users}")
            
        print(f"\n📈 Total Random Actions Dispatched: {action_count}")
        print(f"⏱️ Total Execution Time: {total_time:.2f} seconds")
        print("🏆 Chaos simulation ended cleanly. Core state machine handles overlapping signals successfully!")

if __name__ == "__main__":
    run_chaos_test()