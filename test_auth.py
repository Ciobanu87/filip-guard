
import unittest
from auth import RepairApproval, validate_approval


class TestAuthorization(unittest.TestCase):

    def setUp(self):
        self.site = "https://example.com"
        self.original = "a" * 64
        self.proposed = "b" * 64

    def approval(self, **changes):
        data = {
            "site_url": self.site,
            "resource_id": 10,
            "original_hash": self.original,
            "proposed_hash": self.proposed,
            "authorized": True,
            "approved": True,
        }
        data.update(changes)
        return RepairApproval(**data)

    def check(self, approval):
        return validate_approval(
            approval,
            self.site,
            10,
            self.original,
            self.proposed,
        )

    def test_valid_approval(self):
        self.assertTrue(self.check(self.approval()))

    def test_missing_authorization(self):
        self.assertFalse(
            self.check(self.approval(authorized=False))
        )

    def test_missing_approval(self):
        self.assertFalse(
            self.check(self.approval(approved=False))
        )

    def test_different_website(self):
        self.assertFalse(
            self.check(
                self.approval(
                    site_url="https://other.com"
                )
            )
        )

    def test_different_resource(self):
        self.assertFalse(
            self.check(self.approval(resource_id=99))
        )

    def test_modified_content(self):
        self.assertFalse(
            self.check(
                self.approval(
                    proposed_hash="c" * 64
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
