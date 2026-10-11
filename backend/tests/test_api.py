import unittest
from fastapi.testclient import TestClient
from nexus_app.main import app

from nexus_app.database import engine, Base

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)

    def test_health_check(self):
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertEqual(data["app_name"], "NEXUS SCRAPE AI")

    def test_auth_and_project_lifecycle(self):
        import uuid
        email = f"test_{uuid.uuid4().hex[:8]}@nexusscrape.ai"
        # 1. Register
        reg_res = self.client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Senior Test Engineer"
        })
        self.assertIn(reg_res.status_code, (201, 400))  # 400 if user exists from previous test run

        # 2. Login
        login_res = self.client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create Project
        proj_res = self.client.post("/api/v1/projects", json={
            "name": "E-Commerce Intelligence",
            "description": "Production test project"
        }, headers=headers)
        self.assertEqual(proj_res.status_code, 201)
        project_id = proj_res.json()["id"]

        # 4. List Projects
        list_res = self.client.get("/api/v1/projects", headers=headers)
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(any(p["id"] == project_id for p in list_res.json()))

        # 5. Test SSRF protection on inspect
        inspect_res = self.client.post("/api/v1/inspect", json={
            "url": "http://127.0.0.1:8000/internal",
            "mode": "http"
        }, headers=headers)
        self.assertEqual(inspect_res.status_code, 400)
        self.assertIn("blocked/private address", inspect_res.json()["detail"])

if __name__ == "__main__":
    unittest.main()
