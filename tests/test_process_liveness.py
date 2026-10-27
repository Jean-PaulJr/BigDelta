"""Regression coverage for Windows review polling terminating the server."""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from bigdelta.service import Workspace, _process_alive, _windows_process_alive


class ProcessLivenessTests(unittest.TestCase):
    def test_windows_never_sends_a_signal(self):
        with patch('bigdelta.service.os.name', 'nt'), \
                patch('bigdelta.service._windows_process_alive', return_value=True) as query, \
                patch('bigdelta.service.os.kill') as kill:
            self.assertTrue(_process_alive(123))
        query.assert_called_once_with(123)
        kill.assert_not_called()

    def test_windows_queries_wait_state_and_closes_handle(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = 1234567890123
        for wait_result, alive in ((258, True), (0, False)):
            with self.subTest(wait_result=wait_result), \
                    patch('ctypes.WinDLL', return_value=kernel, create=True):
                kernel.reset_mock()
                kernel.WaitForSingleObject.return_value = wait_result
                self.assertEqual(_windows_process_alive(123), alive)
                kernel.OpenProcess.assert_called_once_with(0x00100000, False, 123)
                kernel.WaitForSingleObject.assert_called_once_with(1234567890123, 0)
                kernel.CloseHandle.assert_called_once_with(1234567890123)

    def test_windows_missing_or_inaccessible_process(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = None
        for error, alive in ((87, False), (5, True)):
            with self.subTest(error=error), \
                    patch('ctypes.WinDLL', return_value=kernel, create=True), \
                    patch('ctypes.get_last_error', return_value=error, create=True):
                self.assertEqual(_windows_process_alive(123), alive)
        kernel.WaitForSingleObject.assert_not_called()
        kernel.CloseHandle.assert_not_called()

    def test_windows_wait_failure_still_closes_handle(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = 123
        kernel.WaitForSingleObject.return_value = 0xFFFFFFFF
        with patch('ctypes.WinDLL', return_value=kernel, create=True), \
                patch('ctypes.get_last_error', return_value=6, create=True), \
                patch('ctypes.WinError', return_value=OSError('invalid handle'), create=True):
            with self.assertRaises(OSError):
                _windows_process_alive(123)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_posix_query_handles_missing_and_denied(self):
        with patch('bigdelta.service.os.name', 'posix'):
            for error, alive in ((None, True), (ProcessLookupError(), False), (PermissionError(), True)):
                with self.subTest(error=error), patch('bigdelta.service.os.kill', side_effect=error) as kill:
                    self.assertEqual(_process_alive(123), alive)
                    kill.assert_called_once_with(123, 0)

    def test_polling_running_job_survives_and_interrupted_job_can_retry(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Workspace(root)
            p = ws.create_project({'name': 'Calculation review'})
            job = dict(id='job1', at='2026-10-27', status='running', owner_pid=os.getpid())
            ws._save_review_job(p['id'], job)
            with patch('bigdelta.service._process_alive', return_value=True):
                self.assertEqual(ws.review_jobs(p['id'])[0]['status'], 'running')
                self.assertEqual(ws._review_job(p['id'], job['id'])['status'], 'running')
            with patch('bigdelta.service._process_alive', return_value=False):
                self.assertEqual(ws.review_jobs(p['id'])[0]['status'], 'failed')
            self.assertEqual(ws._review_job(p['id'], job['id'])['status'], 'failed')
