import unittest
from nexus_app.security.ssrf import validate_url, SSRFSecurityError

class TestSSRFSecurity(unittest.TestCase):
    def test_blocks_loopback(self):
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://127.0.0.1:8080/admin")
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://localhost:5000")

    def test_blocks_private_networks(self):
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://192.168.1.1/router")
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://10.0.0.5:3000/internal")
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://172.16.0.1/")

    def test_blocks_cloud_metadata(self):
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://169.254.169.254/latest/meta-data/")
        with self.assertRaises(SSRFSecurityError):
            validate_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_invalid_schemes(self):
        with self.assertRaises(SSRFSecurityError):
            validate_url("file:///etc/passwd")
        with self.assertRaises(SSRFSecurityError):
            validate_url("ftp://ftp.example.com/file")
        with self.assertRaises(SSRFSecurityError):
            validate_url("javascript:alert(1)")

    def test_blocks_credentials(self):
        with self.assertRaises(SSRFSecurityError):
            validate_url("https://user:password@example.com")

    def test_allows_valid_public_urls(self):
        # example.com resolves to public IP (e.g. 93.184.216.34)
        is_valid, norm = validate_url("https://example.com/articles?page=1")
        self.assertTrue(is_valid)
        self.assertEqual(norm, "https://example.com/articles?page=1")

if __name__ == "__main__":
    unittest.main()
