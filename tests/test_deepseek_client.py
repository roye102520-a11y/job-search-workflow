"""DeepSeek credential and request behavior with synthetic keys only."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import deepseek_client


class DeepSeekClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-deepseek-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / '.config' / 'career-studio' / 'deepseek.json'
        self.path_patch = patch.object(deepseek_client, '_credential_path', return_value=self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_local_key_is_private_replaceable_and_removable(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            deepseek_client.save_local_key('synthetic-deepseek-key-0123456789')
            self.assertEqual(deepseek_client.configured_key(), 'synthetic-deepseek-key-0123456789')
            self.assertEqual(deepseek_client.configuration_status(), {'configured': True, 'source': 'local'})
            if os.name != 'nt':
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
            deepseek_client.save_local_key('synthetic-replacement-key-0123456789')
            self.assertEqual(deepseek_client.configured_key(), 'synthetic-replacement-key-0123456789')
            self.assertTrue(deepseek_client.clear_local_key())
            self.assertFalse(deepseek_client.clear_local_key())
            self.assertFalse(self.path.exists())

    def test_environment_key_keeps_precedence(self):
        deepseek_client.save_local_key('synthetic-local-key-0123456789')
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-env-key-0123456789'}):
            self.assertEqual(deepseek_client.configured_key(), 'synthetic-env-key-0123456789')
            self.assertEqual(deepseek_client.configuration_status()['source'], 'environment')

    def test_complete_uses_private_key_only_in_authorization_header(self):
        deepseek_client.save_local_key('synthetic-deepseek-key-0123456789')

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({'choices': [{'message': {'content': 'synthetic summary'}}]}).encode()

        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}), \
             patch.object(deepseek_client.request, 'urlopen', return_value=FakeResponse()) as urlopen:
            self.assertEqual(deepseek_client.complete('A sufficiently long synthetic prompt for testing.'), 'synthetic summary')
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_header('Authorization'), 'Bearer synthetic-deepseek-key-0123456789')
        self.assertNotIn(b'synthetic-deepseek-key', req.data)

    def test_bad_key_and_symlink_are_rejected(self):
        with self.assertRaises(ValueError):
            deepseek_client.save_local_key('too short')
        self.path.parent.mkdir(parents=True)
        outside = Path(self.tmp.name) / 'outside.json'
        outside.write_text(json.dumps({'api_key': 'synthetic-outside-key-0123456789'}))
        self.path.symlink_to(outside)
        self.assertEqual(deepseek_client._read_local_key(), '')
        with self.assertRaises(ValueError):
            deepseek_client.clear_local_key()

    @unittest.skipIf(os.name == 'nt', 'POSIX permission check')
    def test_world_readable_local_key_is_not_used(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'api_key': 'synthetic-world-readable-key-0123'}))
        self.path.chmod(0o644)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            self.assertEqual(deepseek_client.configured_key(), '')
            self.assertEqual(deepseek_client.configuration_status(), {'configured': False, 'source': None})


if __name__ == '__main__':
    unittest.main()
