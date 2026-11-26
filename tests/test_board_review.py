"""The focused local server must support the current public layout's guest check."""

import unittest

from scripts.phase1_local import create_app


class BoardReviewSandboxTests(unittest.TestCase):
    def test_real_account_routes_report_guest_without_reading_or_creating_users(self):
        app = create_app('sqlite://')
        client = app.test_client()
        for path in ('/api/sfi/profile', '/api/sfi/settings'):
            response = client.get(path)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(client.patch('/api/sfi/settings', json={}).status_code, 401)
        self.assertEqual(client.put('/api/sfi/profile', json={}).status_code, 401)
        self.assertEqual(client.get('/local-demo/').status_code, 404)
        self.assertEqual(client.get('/api/sfi/manufacturer-demo').status_code, 404)
