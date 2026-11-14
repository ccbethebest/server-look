"""Multi-endpoint mapping regression tests."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_mapping_sort import LocalSFTP
from multi_mapping import MultiMapping, migrate_record

class MultiMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('a','b','relay'):
            (self.root/name).mkdir()
        self.mapping=MultiMapping()
        @contextmanager
        def channel(connection):
            yield LocalSFTP(self.root/connection.name)
        self.mapping.channel=channel
        self.connections={name:SimpleNamespace(name=name) for name in ('a','b')}
        self.record=dict(name='test',locations=[dict(server='a',path='/'),dict(server='b',path='/')],source=0,targets=[1],relay=str(self.root/'relay'),direct=False,overwrite=False)

    def test_recursive_remote_relay_is_bounded_and_preserves_existing(self):
        (self.root/'a'/'nested').mkdir()
        data=b'01234567'*400000
        (self.root/'a'/'nested'/'large').write_bytes(data)
        (self.root/'a'/'old').write_text('new')
        (self.root/'b'/'old').write_text('keep')
        self.mapping.chunk_size=1024*1024
        self.mapping.run_many(self.connections,self.record)
        self.assertEqual((self.root/'b'/'nested'/'large').read_bytes(),data)
        self.assertEqual((self.root/'b'/'old').read_text(),'keep')
        self.assertEqual(list((self.root/'relay').iterdir()),[])

    def test_direct_failure_falls_back_and_overwrite_preserves_extra(self):
        (self.root/'a'/'x').write_text('new')
        (self.root/'b'/'x').write_text('old')
        (self.root/'b'/'extra').write_text('keep')
        self.record.update(direct=True,overwrite=True)
        with patch('multi_mapping.direct_copy',side_effect=OSError('unreachable')) as direct:
            result=self.mapping.run_many(self.connections,self.record)
        direct.assert_called_once()
        self.assertIn('中转',result)
        self.assertEqual((self.root/'b'/'x').read_text(),'new')
        self.assertEqual((self.root/'b'/'extra').read_text(),'keep')

    def test_multiple_targets_and_local_source(self):
        local=self.root/'relay'
        (local/'x').write_text('hello')
        self.record['locations'].insert(0,dict(server='local',path=str(local)))
        self.record.update(source=0,targets=[1,2])
        self.mapping.run_many(self.connections,self.record)
        for name in ('a','b'):
            self.assertEqual((self.root/name/'x').read_text(),'hello')

    def test_rejects_nested_target_before_copy(self):
        self.record.update(locations=[dict(server='local',path=str(self.root)),dict(server='local',path=str(self.root/'a'))])
        with self.assertRaisesRegex(ValueError,'子目录'):
            self.mapping.run_many({},self.record)

    def test_cancellation_cleans_staging_and_retains_original(self):
        (self.root/'a'/'x').write_bytes(b'123')
        (self.root/'b'/'x').write_text('original')
        self.record['overwrite']=True
        with patch.object(self.mapping,'relay_copy',side_effect=RuntimeError('cancelled')):
            with self.assertRaises(RuntimeError): self.mapping.run_many(self.connections,self.record)
        self.assertEqual((self.root/'b'/'x').read_text(),'original')
        self.assertEqual([p.name for p in (self.root/'b').iterdir()],['x'])

    def test_old_configuration_migrates(self):
        record=migrate_record(dict(name='old',local='C:/data',remote='/weights',server='server',direction='服务器 → 本地',overwrite=True))
        self.assertEqual(record['locations'][record['source']]['server'],'server')
        self.assertTrue(record['overwrite'])
    def test_insufficient_relay_space_cleans_both_sides(self):
        (self.root/'a'/'x').write_bytes(b'123')
        with patch('multi_mapping.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(OSError,'空间不足'):
                self.mapping.run_many(self.connections,self.record)
        self.assertEqual(list((self.root/'relay').iterdir()),[])
        self.assertEqual(list((self.root/'b').iterdir()),[])

    def test_unused_offline_endpoint_does_not_block_transfer(self):
        (self.root/'a'/'x').write_text('ok')
        self.record['locations'].append(dict(server='offline',path='/'))
        self.mapping.run_many(self.connections,self.record)
        self.assertEqual((self.root/'b'/'x').read_text(),'ok')

    def test_direct_success_does_not_use_relay(self):
        (self.root/'a'/'x').write_text('direct')
        self.record['direct']=True
        def direct(source,target,path,staging,*args,**kwargs):
            (self.root/'b'/staging.lstrip('/')).write_bytes((self.root/'a'/path.lstrip('/')).read_bytes())
        with patch('multi_mapping.direct_copy',side_effect=direct), patch.object(self.mapping,'relay_copy') as relay:
            self.mapping.run_many(self.connections,self.record)
        relay.assert_not_called()
        self.assertEqual((self.root/'b'/'x').read_text(),'direct')

    def test_cancel_during_chunk_removes_spool_and_staging(self):
        (self.root/'a'/'x').write_bytes(b'123')
        original=self.mapping.check
        checks=0
        def cancel():
            nonlocal checks
            checks+=1
            if checks==3:
                self.mapping.cancel()
            original()
        with patch.object(self.mapping,'check',side_effect=cancel):
            with self.assertRaisesRegex(RuntimeError,'取消'):
                self.mapping.run_many(self.connections,self.record)
        self.assertEqual(list((self.root/'relay').iterdir()),[])
        self.assertEqual(list((self.root/'b').iterdir()),[])

    def test_declining_relay_cleans_staging_without_copy(self):
        (self.root/'a'/'x').write_text('secret')
        self.record['direct']=True
        self.mapping.confirm_relay=lambda reason:False
        with patch('multi_mapping.direct_copy',side_effect=OSError('unreachable')), patch.object(self.mapping,'relay_copy') as relay:
            with self.assertRaisesRegex(RuntimeError,'用户取消'):
                self.mapping.run_many(self.connections,self.record)
        relay.assert_not_called()
        self.assertEqual(list((self.root/'b').iterdir()),[])

    def test_speed_reports_bytes_per_elapsed_second(self):
        self.mapping.progress_time=10
        self.mapping.progress_bytes=0
        values=[]
        self.mapping.progress=values.append
        with patch('multi_mapping.time.monotonic',return_value=12):
            self.mapping.report_progress(4*1024*1024)
        self.assertEqual(values,[2.0])
