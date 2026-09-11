FROM python:3.12-slim

# กำหนดโฟลเดอร์ทำงานใน Container
WORKDIR /app

# ก๊อปปี้ไฟล์ requirements.txt มาก่อน (ทริคนี้ช่วยให้ Build รอบต่อไปเร็วขึ้น)
COPY requirements.txt .

# ติดตั้ง Library ต่างๆ
RUN pip install --no-cache-dir -r requirements.txt

# ก๊อปปี้โค้ดทั้งหมดที่เหลือเข้าไป
COPY . .

# คำสั่งรันโปรแกรม
CMD ["python", "main.py"]