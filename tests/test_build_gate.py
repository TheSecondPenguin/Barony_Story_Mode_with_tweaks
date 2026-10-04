"""Reject marker-only, stale or tampered baseline attestations."""
import hashlib
import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('barony_build', Path(__file__).resolve().parents[1] / 'scripts/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BaselineGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'evidence.json'
        (self.root / 'binary').write_bytes(b'test-only binary fixture')
        binary_hash=hashlib.sha256((self.root/'binary').read_bytes()).hexdigest()
        (self.root/'data.json').write_text(json.dumps({'schema':1,'files':[{'path':'fixture','type':'file','size':1,'sha256':hashlib.sha256(b'x').hexdigest()}]}))
        data_hash=hashlib.sha256((self.root/'data.json').read_bytes()).hexdigest()
        marker={'schema':1,'target_os':'test fixture','profile_id':'fixture','purpose':'isolated-barony-playtest','binary_sha256':binary_hash,'source_revision':'pinned','data_manifest_sha256':data_hash}
        (self.root/'marker.json').write_text(json.dumps(marker))
        marker_hash=hashlib.sha256((self.root/'marker.json').read_bytes()).hexdigest()
        self.record = {'schema_version': 1, 'baseline_commit': 'pinned',
                       'evidence_kind':'human_attestation',
                       'producer': 'builder', 'observer':{'id':'independent-qa','role':'QA_AGENT'},
                       'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'platform': 'test fixture', 'data_version': 'fixture',
                       'isolated_profile': 'fixture',
                       'binary':{'path':'binary','sha256':binary_hash},
                       'profile_marker':{'path':'marker.json','sha256':marker_hash},
                       'data_manifest':{'path':'data.json','sha256':data_hash},
                       'data_manifest_sha256':data_hash, 'checks': {}}
        for name in ('build','launch','audio','save_isolation'):
            log={'check':name,'status':'PASS','baseline_commit':'pinned',
                 'binary_sha256':binary_hash,'profile_marker_sha256':marker_hash,
                 'data_manifest_sha256':data_hash,'observer_id':'independent-qa',
                 'observations':['Test fixture only, no actual runtime observation.']}
            p=self.root/(name+'.json'); p.write_text(json.dumps(log))
            self.record['checks'][name]={'status':'PASS','evidence_path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def validate(self):
        self.path.write_text(json.dumps(self.record))
        return build.validate_baseline_evidence(self.path, self.root, 'pinned')

    def test_valid_attestation(self):
        self.assertEqual(self.validate()['baseline_commit'], 'pinned')

    def test_marker_does_not_unlock(self):
        self.record = {}
        with self.assertRaises(RuntimeError): self.validate()

    def test_stale_revision(self):
        self.record['baseline_commit'] = 'old'
        with self.assertRaises(RuntimeError): self.validate()

    def test_unrun_audio_is_blocked(self):
        self.record['checks']['audio']['status'] = 'BLOCKED'
        with self.assertRaises(RuntimeError): self.validate()

    def test_changed_log_is_blocked(self):
        (self.root / 'build.json').write_text('changed')
        with self.assertRaises(RuntimeError): self.validate()

    def test_absolute_log_rejected(self):
        self.record['checks']['build']['evidence_path'] = str(self.root / 'build.json')
        with self.assertRaises(RuntimeError): self.validate()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'log'
            external.write_text('external')
            (self.root / 'escape').symlink_to(external)
            self.record['checks']['build']['evidence_path'] = 'escape'
            with self.assertRaises(RuntimeError): self.validate()

    def test_builder_cannot_attest_independently(self):
        self.record['observer']['id']='builder'
        with self.assertRaises(RuntimeError): self.validate()

    def test_arbitrary_text_cannot_be_runtime_observation(self):
        p=self.root/'build.json'; p.write_text('PASS')
        self.record['checks']['build']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaises(RuntimeError): self.validate()

    def test_future_timestamp(self):
        self.record['recorded_at']='2099-01-01T00:00:00Z'
        with self.assertRaises(RuntimeError): self.validate()

    def test_binary_changed(self):
        (self.root/'binary').write_bytes(b'different')
        with self.assertRaises(RuntimeError): self.validate()

    def test_mismatched_profile_subject(self):
        self.record['profile_marker']['sha256']='f'*64
        with self.assertRaises(RuntimeError): self.validate()

    def test_missing_data_manifest(self):
        (self.root/'data.json').unlink()
        with self.assertRaises(RuntimeError): self.validate()

    def test_changed_data_manifest(self):
        (self.root/'data.json').write_text('{}')
        with self.assertRaises(RuntimeError): self.validate()


if __name__ == '__main__':
    unittest.main()
