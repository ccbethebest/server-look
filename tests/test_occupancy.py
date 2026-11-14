import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from server_look.remote.server_resources import accelerator_occupancy
from server_look.ui.server_tabs import ServerTabs
from server_look.app.desktop_app import MultiServerApp


class OccupancyTests(unittest.TestCase):
    def test_distinct_physical_cards_and_three_states(self):
        raw = '| 0 910B | OK |\n| 1 910B | OK |'
        cases = [({}, 'idle', 0), ({1: {'0:0': 10}, 2: {'0:1': 20}}, 'partial', 1),
                 ({1: {'0:0': 10, '1:0': 20}}, 'full', 2)]
        for tasks, state, used in cases:
            with self.subTest(state=state):
                result = accelerator_occupancy(raw, tasks, {})
                self.assertEqual((result['state'], result['used'], result['total']), (state, used, 2))
                self.assertFalse(result['errors'])

    def test_mixed_vendors_and_unknown_devices(self):
        hardware = {'GPU 0': 'A100', 'GPU 1': 'A100', 'GPU 数量': '2'}
        result = accelerator_occupancy('| 0 910B | OK |', {1: {'GPU 0': 1, '0:0': 1}}, hardware)
        self.assertEqual((result['state'], result['used'], result['total']), ('partial', 2, 3))
        self.assertTrue(accelerator_occupancy('', {}, {})['errors'])
        self.assertTrue(accelerator_occupancy('', {1: {'MIG-unknown': 1}}, hardware)['errors'])
        self.assertEqual(accelerator_occupancy('', {1: {'GPU 0': 1, 'GPU 1': 1}}, hardware)['state'], 'full')

    def test_one_click_queries_every_connected_server(self):
        pages = [SimpleNamespace(root=str(i), connection=True, connection_state=Mock(),
                                 idle_pending=False, status=Mock(), submit=Mock()) for i in range(3)]
        for page in pages:
            page.connection_state.get.return_value = '连接成功'
        offline = SimpleNamespace(root='offline', connection=None, submit=Mock())
        app = SimpleNamespace(pages={p.root: p for p in [*pages, offline]}, occupancy_marks={},
                              occupancy_details={}, server_tabs=Mock())
        MultiServerApp.query_idle(app)
        for page in pages:
            page.submit.assert_called_once_with('idle')
            self.assertTrue(page.idle_pending)
            self.assertIn('正在查询', app.occupancy_details[page.root])
        offline.submit.assert_not_called()

    def test_marks_and_click_clear_including_current_tab(self):
        app = SimpleNamespace(occupancy_marks={}, occupancy_details={}, server_tabs=Mock(), notebook=Mock())
        page = SimpleNamespace(root='tab1', status=Mock(), idle_pending=True)
        for state in ('idle', 'partial', 'full'):
            MultiServerApp.idle_result(app, page, dict(state=state, used=1, total=2, errors=[]), '')
            self.assertEqual(app.occupancy_marks['tab1'], state)
            tabs = SimpleNamespace(app=app, draw=Mock())
            ServerTabs.select(tabs, 'tab1')
            self.assertNotIn('tab1', app.occupancy_marks)
            self.assertIn('1/2', app.occupancy_details['tab1'])
        app.occupancy_marks['tab1'] = 'idle'
        MultiServerApp.idle_result(app, page, {'errors': ['probe failed']}, '')
        self.assertNotIn('tab1', app.occupancy_marks)


if __name__ == '__main__':
    unittest.main()
