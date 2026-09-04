import requests
import time
import sys
import random

# BASE_URL = "http://localhost:8000"
BASE_URL = "http://192.168.10.210:8000"

def print_header(msg):
    print(f"\n{'='*50}\n▶ {msg}\n{'='*50}")

def run_queue_loop_test(delay_between_loops=2):
    iteration = 1
    success_count = 0
    fail_count = 0

    print("🚀 เริ่มการทดสอบระบบคิวแบบวนลูปต่อเนื่อง (Queue Loop Test)...")
    print("💡 [กดปุ่ม Ctrl+C ที่คีย์บอร์ดเพื่อสั่งหยุดการทดสอบได้ทุกเมื่อ]")
    time.sleep(2)

    try:
        while True:
            print_header(f"🔄 เริ่มการทดสอบรอบที่ {iteration}")
            try:
                # 1. ดึงข้อมูลระบบ
                res = requests.get(f"{BASE_URL}/slots")
                res.raise_for_status()
                data = res.json()
                
                # ตั้งค่าเซิร์ฟเวอร์ให้อยู่ใน Manual Mode (ปิดเซนเซอร์) เพื่อทดสอบการกดแบบแมนนวล
                requests.post(f"{BASE_URL}/config/update", json={
                    "users": data.get("users", []),
                    "slots": data.get("slots", []),
                    "use_sensor": False
                })
                
                users = data.get("users", [])
                if len(users) < 3:
                    print("❌ ต้องการ User อย่างน้อย 3 คนใน config.json เพื่อทดสอบคิว")
                    sys.exit(1)
                    
                # 🎲 สุ่มผู้ใช้งาน 3 คนที่ไม่ซ้ำกัน
                random.shuffle(users)
                u1 = users[0]["user_id"]
                u2 = users[1]["user_id"]
                u3 = users[2]["user_id"]

                # 🎲 สุ่ม Slot
                test_slot = random.choice(data["slots"])
                point_name = test_slot["point_name"]
                
                allowed_items = test_slot.get("allowed_item", [])
                item_type = random.choice(allowed_items) if (allowed_items and "*" not in allowed_items) else "box"

                print(f"✅ สล็อต: '{point_name}' | Item: '{item_type}'")
                print(f"✅ คิวผู้เล่น: 1.[{u1}] -> 2.[{u2}] -> 3.[{u3}]")

                # 2. Reset สล็อต (เคลียร์ช่อง)
                requests.post(f"{BASE_URL}/slot/reset", json={"point_name": point_name})
                time.sleep(1)

                # 3. U1 จองและวางของจนเต็ม
                requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item_type, "user_id": u1, "note": f"Loop {iteration} - Owner"})
                requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                print(f"⏳ [FULL] {u1} วางของสำเร็จ")
                time.sleep(1.5) # UI จะโชว์ FULL

                # 4. U2 ขอเข้าคิว
                res2 = requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item_type, "user_id": u2, "note": "Queue 1"}).json()
                assert res2.get("status") == "QUEUED", f"U2 Failed to queue"
                print(f"⏳ [QUEUED] {u2} เข้าคิวที่ 1")
                time.sleep(1.5) # UI จะโชว์ U2 ใน Queue slot

                # 5. U3 ขอเข้าคิว
                res3 = requests.post(f"{BASE_URL}/slot/drop", json={"point_name": point_name, "item_type": item_type, "user_id": u3, "note": "Queue 2"}).json()
                assert res3.get("status") == "QUEUED", f"U3 Failed to queue"
                print(f"⏳ [QUEUED] {u3} เข้าคิวที่ 2")
                time.sleep(2.5) # UI จะโชว์ U2 และ U3 ใน Queue slot

                # 6. U1 หยิบของออก
                requests.post(f"{BASE_URL}/item/pickup", json={"item_type": item_type, "user_id": u1})
                requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                print(f"⏳ {u1} หยิบของออกแล้ว! รอระบบดึงคิวอัตโนมัติ...")
                time.sleep(2) # รอระบบประมวลผลการดึงคิว และให้ UI อัปเดต

                # 7. ตรวจสอบความถูกต้องของการดึงคิว (ควรอยู่ในสถานะ DROP_RESERVED ของ U2)
                slots_state = requests.get(f"{BASE_URL}/slots").json()["slots"]
                current_slot = next(s for s in slots_state if s["point_name"] == point_name)
                
                assert current_slot['status'] == "DROP_RESERVED", f"Slot status should be DROP_RESERVED, but got {current_slot['status']}"
                assert current_slot.get('reserved_for') == u2, f"Slot should be reserved for {u2}, but got {current_slot.get('reserved_for')}"
                
                # 8. U2 ยืนยันการวางของในสล็อต (Confirm Drop)
                requests.post(f"{BASE_URL}/slot/confirm", json={"point_name": point_name})
                print(f"⏳ [FULL] {u2} ยืนยันการวางของสำเร็จ")
                time.sleep(1.5)

                # 9. ตรวจสอบสถานะว่าสล็อตเต็มจริง และเป็นของ U2
                slots_state = requests.get(f"{BASE_URL}/slots").json()["slots"]
                current_slot = next(s for s in slots_state if s["point_name"] == point_name)
                assert current_slot['status'] == "FULL", f"Slot status should be FULL after confirmation, but got {current_slot['status']}"
                assert current_slot['items'][0].get('user_id') == u2, f"Item owner should be {u2}, but got {current_slot['items'][0].get('user_id')}"
                
                print(f"🎉 รอบที่ {iteration} สำเร็จ 100%! ระบบดึง {u2} จากคิวขึ้นมาจองและยืนยันด้วยมือสำเร็จ")
                success_count += 1

            except AssertionError as e:
                print(f"\n❌ TEST FAILED (รอบที่ {iteration}): {e}")
                fail_count += 1
            except Exception as e:
                print(f"\n❌ ERROR (รอบที่ {iteration}): {e}")
                fail_count += 1

            print(f"⏳ รอ {delay_between_loops} วินาทีก่อนสุ่มเริ่มรอบใหม่...")
            time.sleep(delay_between_loops)
            iteration += 1

    except KeyboardInterrupt:
        print("\n\n🛑 ได้รับสัญญาณหยุด (Ctrl+C)")
    finally:
        print_header("📊 สรุปผลการทดสอบระบบคิว (QUEUE TEST SUMMARY)")
        print(f"🔄 จำนวนรอบทั้งหมดที่รัน: {iteration - 1}")
        print(f"✅ ผ่าน (Success): {success_count}")
        print(f"❌ ไม่ผ่าน (Failed): {fail_count}")
        print("="*50)

if __name__ == "__main__":
    # สามารถปรับ delay เป็นตัวเลขน้อยลงได้ ถ้ารู้สึกว่ามันรันช้าไปครับ
    run_queue_loop_test(delay_between_loops=2)