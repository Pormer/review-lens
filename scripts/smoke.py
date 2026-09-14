"""Exercise a running server without external API calls. Used in Docker CI."""
import time

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        for _ in range(30):
            try:
                client.get("/healthz").raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            raise RuntimeError("Health check failed")
        response = client.post("/api/analyses", json={"product_name": "demo", "product_url": "https://example.com", "mode": "demo"})
        response.raise_for_status()
        job_id = response.json()["id"]
        for _ in range(40):
            job = client.get(f"/api/analyses/{job_id}").json()
            if job["status"] == "completed":
                assert job["report"]["mode"] == "demo"
                assert job["report"]["metrics"]["paired_count"] == 8
                client.get(f"/api/analyses/{job_id}/markdown").raise_for_status()
                client.delete(f"/api/analyses/{job_id}").raise_for_status()
                print("PASS: health, demo job, metrics, export, deletion")
                return
            if job["status"] == "failed":
                raise RuntimeError(job["error"])
            time.sleep(.5)
        raise RuntimeError("Demo job timed out")


if __name__ == "__main__":
    main()
