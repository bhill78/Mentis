"""Exercise the existing handler and artifact helpers on a disposable synthetic Brain.
No HTTP listener, runtime execution, credentials, or production records.
"""
import pathlib
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from mentis import artifacts
from mentis.spine import held
from mentis.web import _Handler, fixture
from mentis.worker import CAPABILITY_HEADER


class DescribeRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(tempfile.mkdtemp(prefix='describe-brain-', dir=pathlib.Path(__file__).parent))
        cls.world = fixture.build(str(cls.root))
        cls.corpus, cls.cv = cls.world['corpus'], cls.world['cv']
        cls.actor = cls.world['who']['@brian']
        print('synthetic fixture:', cls.root)

    def hold(self, data):
        return artifacts.hold(self.corpus, self.cv, data, act=artifacts.SUBMITTED,
                              actor=self.actor, source='independent synthetic review', door='human',
                              claimed_name='claimed.png', claimed_media_type='image/png')

    def answer(self, ref, headers=None):
        out = []
        handler = types.SimpleNamespace(headers=headers or {}, state=types.SimpleNamespace(corpus=self.corpus),
                                        _artifact_send=lambda status, body: out.append((status, body)))
        _Handler._artifact(handler, ref, describe=True)
        self.assertEqual(len(out), 1)
        return out[0]

    def test_held_exact_identity_verified_treatment_and_no_bytes(self):
        a = self.hold(b'An actual text report, not an image.\n')
        status, d = self.answer(a['admission'])
        self.assertEqual(status, 200)
        self.assertEqual(d['ref'], a['admission'])
        self.assertEqual(d['state'], 'held')
        self.assertEqual(d['treatment']['view'], 'text')
        self.assertEqual(d['url'], '/api/artifacts/' + a['admission'])
        self.assertNotIn('_bytes', d)
        self.assertNotIn('source', d)
        print('verified description:', d)

    def test_worker_grant_still_refused(self):
        status, d = self.answer('adm-111111111111', {CAPABILITY_HEADER:'synthetic-not-a-grant'})
        self.assertEqual(status, 403)
        self.assertIn('/api/worker', d['error'])

    def test_unknown_is_explicit(self):
        status, d = self.answer('adm-111111111111')
        self.assertEqual(status, 200)
        self.assertEqual(d['state'], 'unknown')

    def test_purged_is_explicit(self):
        a = self.hold(b'purge only these synthetic fixture bytes\n')
        artifacts.purge(self.corpus, self.cv, a['admission'], by=self.actor, because='synthetic review fixture')
        status, d = self.answer(a['admission'])
        self.assertEqual(status, 200)
        self.assertEqual(d['state'], 'purged')
        self.assertNotIn('_bytes', d)

    def test_missing_is_explicit(self):
        a = self.hold(b'missing fixture bytes\n')
        path = self.root / held.STORE / a['digest'][:2] / a['digest']
        path.unlink()
        status, d = self.answer(a['admission'])
        self.assertEqual(status, 200)
        self.assertEqual(d['state'], 'held-but-missing')

    def test_corrupt_is_explicit(self):
        a = self.hold(b'corrupt fixture bytes\n')
        path = self.root / held.STORE / a['digest'][:2] / a['digest']
        path.write_bytes(b'changed synthetic fixture content\n')
        status, d = self.answer(a['admission'])
        self.assertEqual(status, 200)
        self.assertEqual(d['state'], 'held-but-corrupt')


if __name__ == '__main__':
    unittest.main(verbosity=2)
