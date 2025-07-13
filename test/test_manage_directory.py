import os
import tempfile
import unittest
from unittest.mock import patch

class DummyLogger:
    logs = []

    @classmethod
    def log(cls, message, level=None):
        cls.logs.append((message, level))


class ManageDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from helpers import system_utils as su
        self.su = su
        self.patcher = patch.object(self.su, 'Logger', DummyLogger)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_manage_directory_creates_folder_posix(self):
        workspace = os.path.join(self.tmp.name, 'ws')
        os.makedirs(workspace)
        self.su.manage_directory(workspace, del_part_log=False)
        expected = os.path.join(workspace, 'IB_Tool_Results')
        self.assertTrue(os.path.isdir(expected))

if __name__ == '__main__':
    unittest.main()
