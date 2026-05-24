#!/usr/bin/env python

# Fast tests (no network). Run by CI before deploy.
# .venv/bin/python -m unittest test_fast -v

import os
import unittest

os.environ.setdefault("FLASK_SECRET_KEY", "test")


class AppImportTest(unittest.TestCase):
    def test_app_imports(self):
        import app
        from flask import Flask
        self.assertIsInstance(app.app, Flask)


if __name__ == "__main__":
    unittest.main()
