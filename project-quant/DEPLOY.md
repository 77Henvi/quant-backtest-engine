# Deploy to GCP — Step by Step

⚠️ **ต้องรันคำสั่งพวกนี้บนเครื่องคุณเอง** (ไม่ใช่ในนี้) เพราะต้องมี GCP account, gcloud CLI, และ credential จริง

## เตรียมของก่อน (ครั้งเดียว)

1. สมัคร GCP project (ถ้ายังไม่มี) ที่ https://console.cloud.google.com
2. ติดตั้ง gcloud CLI: https://cloud.google.com/sdk/docs/install
3. ติดตั้ง Terraform: https://developer.hashicorp.com/terraform/install
4. ติดตั้ง Docker Desktop: https://www.docker.com/products/docker-desktop
5. Login:
   ```
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project YOUR_PROJECT_ID
   ```

## ขั้นตอนที่ 1: สร้าง Infrastructure ด้วย Terraform

```bash
cd infra

# ตั้งรหัสผ่าน DB ผ่าน environment variable (ห้าม hardcode ในไฟล์!)
export TF_VAR_db_password="เลือกรหัสผ่านที่ปลอดภัย"
export TF_VAR_project_id="your-project-id"
export TF_VAR_container_image="asia-southeast1-docker.pkg.dev/your-project-id/quant-repo/backend:latest"

terraform init
terraform plan    # ดูก่อนว่าจะสร้างอะไรบ้าง
terraform apply   # พิมพ์ yes เพื่อยืนยัน
```

**หมายเหตุ**: รอบแรกที่ apply, Cloud Run service จะ deploy fail เพราะ image ยังไม่มีใน Artifact Registry (ทำขั้นตอนที่ 2 ก่อน แล้วค่อย apply ใหม่อีกรอบ)

## ขั้นตอนที่ 2: Build และ Push Docker Image

```bash
cd ../backend

# ตั้งค่า Docker ให้ auth กับ Artifact Registry
gcloud auth configure-docker asia-southeast1-docker.pkg.dev

# Build image (ใช้ path เดียวกับ TF_VAR_container_image ด้านบน)
docker build -t asia-southeast1-docker.pkg.dev/your-project-id/quant-repo/backend:latest .

# ทดสอบรันบนเครื่องตัวเองก่อน push
docker run -p 8080:8080 asia-southeast1-docker.pkg.dev/your-project-id/quant-repo/backend:latest
# เปิด http://localhost:8080/health ต้องเห็น {"status":"ok"}
# กด Ctrl+C เพื่อหยุด

docker push asia-southeast1-docker.pkg.dev/your-project-id/quant-repo/backend:latest
```

## ขั้นตอนที่ 3: Apply Terraform อีกครั้ง (ตอนนี้ image มีแล้ว)

```bash
cd ../infra
terraform apply
```

จบแล้วจะเห็น output แบบนี้:
```
cloud_run_url = "https://quant-api-xxxxx-as.a.run.app"
```

เปิด URL นั้น + `/health` ใน browser ต้องเห็น `{"status":"ok"}` — แปลว่า deploy สำเร็จ

## เช็คว่าเชื่อม Postgres จริงได้ไหม

```bash
curl https://quant-api-xxxxx-as.a.run.app/backtests/strategies
```
ถ้าได้ `["fibonacci_retracement","sma_crossover"]` กลับมา แปลว่า API + Database บน cloud ทำงานครบวงจรแล้ว

## ค่าใช้จ่ายโดยประมาณ

- Cloud Run: scale-to-zero เมื่อไม่มีคนใช้ = ฟรีเกือบทั้งหมดสำหรับ portfolio project
- Cloud SQL (`db-f1-micro`): ค่าใช้จ่ายคงที่รายชั่วโมง ~$7-10/เดือน แม้ไม่มีคนใช้ (นี่คือค่าใช้จ่ายหลักที่ต้องระวัง)
- **แนะนำ**: รัน `terraform destroy` ทันทีหลังจากถ่ายภาพ/อัดวิดีโอ demo เสร็จ เพื่อไม่ให้ Cloud SQL คิดเงินต่อเนื่อง

```bash
cd infra
terraform destroy   # ลบทุกอย่างทิ้ง เมื่อไม่ใช้แล้ว
```

## ถ้าเจอ error

Copy ข้อความ error เต็มๆ มาถามได้เลย — error ตอน deploy จริงเป็นเรื่องปกติมาก โดยเฉพาะเรื่อง permission/API ยังไม่เปิดใช้งาน
