"""Independent mapping rows and compatibility with older multi-target records."""
import unittest
from mapping_rows import expand_records, direction_label, server_label


class MappingRowsTests(unittest.TestCase):
    def test_old_targets_become_independent_pairs(self):
        old = dict(name='old', locations=[dict(server='local', path='C:/data'),
            dict(server='a', path='/a'), dict(server='b', path='/b')], source=0,
            targets=[1, 2], overwrite=True, relay='C:/tmp')
        rows = expand_records([old])
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['locations'][1]['server'] for row in rows], ['a', 'b'])
        self.assertTrue(all(row['source'] == 0 and row['targets'] == [1] for row in rows))
        rows[0]['locations'][0]['path'] = 'changed'
        self.assertEqual(rows[1]['locations'][0]['path'], 'C:/data')
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])

    def test_ids_survive_reload_and_direction_displays_endpoints(self):
        row = dict(id='saved', name='pair', locations=[dict(server='host|a', path='/a'),
            dict(server='local', path='C:/b')], source=0, targets=[1])
        self.assertEqual(expand_records([row])[0]['id'], 'saved')
        self.assertEqual(direction_label(row), 'a → 本机')

    def test_server_labels_show_account_and_nondefault_port(self):
        self.assertEqual(server_label('22|-l|root|server.example'),'root@server.example')
        self.assertEqual(server_label('2222|-l|user|server.example'),'user@server.example:2222')
