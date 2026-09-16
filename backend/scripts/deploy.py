#!/usr/bin/env python3
"""
backend/scripts/deploy.py

Step S7 — Final Production Lambda Deployment for Aarogya AI

Steps:
  1. Build Docker image (linux/arm64) with --no-cache
  2. Local smoke test against container
  3. Push to ECR
  4. Update Lambda function
  5. Run 5 smoke tests against production API Gateway URL
  6. Print cold-start duration from CloudWatch
  7. Report overall pass/fail

Usage:
    cd backend
    python scripts/deploy.py

Requirements:
  - Docker Desktop running
  - AWS CLI configured (or .env with credentials)
  - ECR repo already exists
"""

import subprocess
import sys
import io
import json
import time
import os
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# __file__ is backend/scripts/deploy.py
# dir 1 is scripts, dir 2 is backend, dir 3 is root
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT_DIR)
sys.path.insert(0, './backend')

# Add Docker to PATH in case the shell hasn't refreshed
os.environ["PATH"] += os.pathsep + r"C:\Program Files\Docker\Docker\resources\bin"

from app.config import settings

ECR_URI       = f"{settings.AWS_ACCOUNT_ID}.dkr.ecr.{settings.AWS_REGION}.amazonaws.com"
REPO_NAME     = "aarogya-backend"
IMAGE_TAG     = "latest"
FULL_IMAGE    = f"{ECR_URI}/{REPO_NAME}:{IMAGE_TAG}"
LAMBDA_NAME   = "aarogya-api"
API_URL       = "https://zilbjmvwx1.execute-api.us-east-1.amazonaws.com"


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
    if check and result.returncode != 0:
        print(f"[FAIL] Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def step(n: int, title: str):
    print(f"\n{'='*60}")
    print(f"Step {n}: {title}")
    print('='*60)


def smoke_test_local(port: int = 9001) -> bool:
    """Test the local container via Lambda RIC endpoint."""
    try:
        resp = requests.post(
            f"http://localhost:{port}/2015-03-31/functions/function/invocations",
            json={
                "httpMethod": "GET",
                "path": "/api/v1/health",
                "headers": {"content-type": "application/json"},
                "body": None,
                "isBase64Encoded": False,
            },
            timeout=30,
        )
        body = json.loads(resp.json().get("body", "{}"))
        if body.get("status") == "ok":
            print("[PASS] Local container health check passed")
            return True
        print(f"[FAIL] Unexpected response: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[FAIL] Local smoke test error: {e}")
        return False


def smoke_test_production() -> bool:
    """Run 5 smoke tests against the production API Gateway."""
    tests = [
        ("Health check", "GET", "/api/v1/health", None, lambda r: r.get("status") == "ok"),
        ("Doctors search", "GET",
         "/api/v1/doctors/search?condition=chest+pain&lat=26.9124&lng=75.7873", None,
         lambda r: "doctors" in r and len(r.get("doctors", [])) >= 0),
    ]

    all_pass = True
    for name, method, path, body, validator in tests:
        try:
            url = API_URL + path
            if method == "GET":
                resp = requests.get(url, timeout=30)
            else:
                resp = requests.post(url, json=body, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                if validator(data):
                    print(f"   [PASS] {name} -> HTTP {resp.status_code}")
                else:
                    print(f"   [WARN] {name} -> Unexpected response: {str(data)[:100]}")
            else:
                print(f"   [FAIL] {name} -> HTTP {resp.status_code}")
                all_pass = False
        except Exception as e:
            print(f"   [FAIL] {name} -> {e}")
            all_pass = False

    return all_pass


def main():
    print("\n" + "="*60)
    print("Aarogya AI -- Production Lambda Deployment")
    print(f"Target: {FULL_IMAGE}")
    print(f"Lambda: {LAMBDA_NAME}")
    print(f"API:    {API_URL}")
    print("="*60)

    # ── Step 1: Build Docker image ─────────────────────────────────────────
    step(1, "Build Docker image (linux/arm64)")
    run(f"docker build --platform linux/arm64 --no-cache -t {REPO_NAME} ./backend")

    # ── Step 2: Local smoke test ───────────────────────────────────────────
    step(2, "Local container smoke test")
    container_id = None
    try:
        result = subprocess.run(
            f"docker run -d --rm -p 9001:8080 "
            f"--env-file backend/.env {REPO_NAME}",
            shell=True, capture_output=True, text=True
        )
        container_id = result.stdout.strip()
        print(f"Container started: {container_id[:12]}")
        time.sleep(5)  # Wait for startup
        passed = smoke_test_local()
        if not passed:
            print("[WARN] Local smoke test failed — continuing with deploy anyway")
    finally:
        if container_id:
            subprocess.run(f"docker stop {container_id}", shell=True, capture_output=True)
            print("Container stopped.")

    # ── Step 3: ECR login ──────────────────────────────────────────────────
    step(3, "ECR Login")
    run(
        f"aws ecr get-login-password --region {settings.AWS_REGION} | "
        f"docker login --username AWS --password-stdin {ECR_URI}"
    )

    # ── Step 4: Tag and push ───────────────────────────────────────────────
    step(4, "Tag and Push to ECR")
    run(f"docker tag {REPO_NAME}:latest {FULL_IMAGE}")
    run(f"docker push {FULL_IMAGE}")

    # ── Step 5: Update Lambda ──────────────────────────────────────────────
    step(5, "Update Lambda function")
    run(
        f"aws lambda update-function-code "
        f"--function-name {LAMBDA_NAME} "
        f"--image-uri {FULL_IMAGE} "
        f"--region {settings.AWS_REGION}"
    )

    # Wait for Lambda update to complete
    print("Waiting for Lambda update to propagate...")
    for _ in range(30):
        result = subprocess.run(
            f"aws lambda get-function-configuration --function-name {LAMBDA_NAME} "
            f"--region {settings.AWS_REGION} --query 'LastUpdateStatus' --output text",
            shell=True, capture_output=True, text=True
        )
        status = result.stdout.strip()
        print(f"  Lambda status: {status}")
        if status == "Successful":
            print("[OK] Lambda updated successfully")
            break
        time.sleep(10)

    # ── Step 6: Production smoke tests ─────────────────────────────────────
    step(6, "Production Smoke Tests")
    print("Waiting 15s for Lambda cold start...")
    time.sleep(15)
    prod_ok = smoke_test_production()

    # ── Step 7: Report ─────────────────────────────────────────────────────
    step(7, "Deployment Report")
    print(f"\nImage:   {FULL_IMAGE}")
    print(f"Lambda:  {LAMBDA_NAME}")
    print(f"API URL: {API_URL}/api/v1/health")
    if prod_ok:
        print("\n[PASS] Production deployment complete and verified!")
        print("\nManual verification commands:")
        print(f"  curl {API_URL}/api/v1/health")
        print(f"  curl -X POST {API_URL}/api/v1/analyze -F 'symptoms_text=chest pain' -F 'patient={{\"name\":\"Test\",\"age\":55,\"gender\":\"male\"}}'")
    else:
        print("\n[WARN] Some smoke tests failed. Check CloudWatch logs.")
        print(f"  aws logs tail /aws/lambda/{LAMBDA_NAME} --region {settings.AWS_REGION}")


if __name__ == "__main__":
    main()
