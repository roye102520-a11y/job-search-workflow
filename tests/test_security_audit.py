"""Conditional LAN-mode exposure: synthetic HTTP reproduction, never real data."""
import http.client
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from resume_server import StudioServer


class NetworkExposureAuditTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_lan_mode_must_not_give_new_unauthenticated_client_candidate_data(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-lan-audit-') as name:
            case = Path(name) / 'case'
            shutil.copytree(Path(__file__).parent / 'fixtures/synthetic-case', case)
            server = StudioServer(case, port=0, host='0.0.0.0')
            worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
            worker.start()
            try:
                def get(path, headers=None):
                    client = http.client.HTTPConnection('127.0.0.1', server.server_port)
                    try:
                        client.request('GET', path, headers=headers or {})
                        response = client.getresponse()
                        return response.status, response.read()
                    finally: client.close()
                status, data = get('/api/bootstrap')
                token = json.loads(data).get('token') if status == 200 else ''
                status, data = get('/api/workspace', {'X-Local-Token': token})
                # Local HTTP simulates a new client in explicitly enabled LAN mode.
                # This is not proof of public internet reachability or default-mode exposure.
                self.assertIn(status, (401, 403))
            finally:
                server.shutdown(); server.server_close(); worker.join(2)
