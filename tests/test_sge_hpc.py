"""Offline behavior tests; never connect to a real server."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'sge_hpc.py'
spec = importlib.util.spec_from_file_location('sge_hpc', SCRIPT)
hpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hpc)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / 'code with spaces'
        self.local.mkdir()
        (self.local / 'job.sge').write_bytes(b'#!/bin/bash\n#$ -o logs/\necho ok\n')
        self.config = self.root / 'config.json'
        self.cfg = dict(target='lab-alias', shared_root='/shared/user/jobs',
                        sge_bin_dirs=[], exclude=[], max_upload_mb=100)
        self.config.write_text(json.dumps(self.cfg), encoding='utf-8')

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            hpc.main(['--config', str(self.config), *args])
        return output.getvalue()

    def transfer_args(self, action):
        return [action, '--local', str(self.local), '--remote', '/shared/user/jobs/run 1']

    def test_unconfigured_distribution_cannot_connect(self):
        example = SCRIPT.parents[1] / 'assets' / 'config.example.json'
        with patch.object(hpc.Remote, 'run') as remote, self.assertRaises(ValueError):
            hpc.main(['--config', str(example), 'preflight'])
        remote.assert_not_called()

    def test_doctor_needs_no_config_and_never_calls_ssh(self):
        with patch.object(hpc.shutil, 'which', side_effect=lambda name: '/tools/' + name), \
                patch.object(hpc.subprocess, 'run') as run, \
                patch.object(hpc, 'load_config') as config, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            hpc.main(['doctor'])
        config.assert_not_called()
        run.assert_not_called()
        self.assertIn('ssh: /tools/ssh', output.getvalue())

    def test_doctor_explains_missing_ssh(self):
        with patch.object(hpc.shutil, 'which', return_value=None), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                self.assertRaisesRegex(ValueError, 'OpenSSH client not found'):
            hpc.main(['doctor'])
        self.assertIn('ssh: NOT FOUND', output.getvalue())

    def test_preflight_still_requires_configuration(self):
        with contextlib.redirect_stderr(io.StringIO()), \
                patch.object(hpc.Remote, 'run') as remote, self.assertRaises(SystemExit) as exc:
            hpc.main(['preflight'])
        self.assertEqual(exc.exception.code, 2)
        remote.assert_not_called()

    def test_dry_run_selects_small_input_without_ssh_or_writes(self):
        for folder in ('data', '.git', 'results', 'input'):
            (self.local / folder).mkdir()
            (self.local / folder / 'file.txt').write_text('small')
        (self.local / '.env').write_text('SECRET=hidden')
        with patch.object(hpc.Remote, 'run') as remote:
            output = self.run_cli(*self.transfer_args('submit'), '--job', 'job.sge', '--dry-run')
        remote.assert_not_called()
        self.assertIn('input/file.txt', output)
        self.assertNotIn('data/file.txt', output)
        self.assertNotIn('results/file.txt', output)
        self.assertNotIn('.env', output)

    def test_submit_without_authorization_has_no_side_effects(self):
        with patch.object(hpc.Remote, 'run') as remote, self.assertRaises(ValueError):
            self.run_cli(*self.transfer_args('submit'), '--job', 'job.sge')
        remote.assert_not_called()

    def test_size_limit_stops_before_remote_mutation(self):
        self.cfg['max_upload_mb'] = 0.000001
        self.config.write_text(json.dumps(self.cfg))
        with patch.object(hpc.Remote, 'run') as remote, self.assertRaises(ValueError):
            self.run_cli(*self.transfer_args('sync'))
        remote.assert_not_called()

    def test_upload_archive_and_array_job_id(self):
        commands = []

        def fake(command, **kw):
            commands.append(command)
            if 'stdin' in kw:
                with tarfile.open(fileobj=kw['stdin'], mode='r:gz') as tf:
                    self.assertEqual(tf.getnames(), ['job.sge'])
            return '789.1-10:1\n' if 'qsub' in command else ''

        with patch.object(hpc.Remote, 'run', side_effect=fake):
            output = self.run_cli(*self.transfer_args('submit'), '--job', 'job.sge', '--approved')
        self.assertIn('JOBID=789', output)
        self.assertEqual(len(commands), 2)
        self.assertIn('mkdir -p logs && qsub -terse job.sge', commands[1])

    def test_status_uses_remote_authenticated_user_and_keeps_all_array_rows(self):
        lines = '123 0.5 array user r date queue 1 1\n123 0.5 array user qw date queue 1 2\n'
        with patch.object(hpc.Remote, 'run', return_value=lines) as remote:
            output = self.run_cli('status', '123')
        remote.assert_called_once_with('qstat -u "$(id -un)"')
        self.assertEqual(output.count('123'), 2)

    QACCT = ('==============================================================\n'
             'qname        all.q\nhostname     node1\nowner        user\njobname      array\n'
             'jobnumber    123\ntaskid       1\ncpu          1.000\nexit_status  0\n'
             'maxvmem      1.000G\n'
             '==============================================================\n'
             'jobname      array\njobnumber    123\ntaskid       2\nexit_status  1\n')

    def fake_finished(self, qacct):
        return lambda command, **kw: qacct if command.startswith('qacct') else ''

    def test_status_shows_accounting_summary_per_record(self):
        with patch.object(hpc.Remote, 'run', side_effect=self.fake_finished(self.QACCT)) as remote:
            output = self.run_cli('status', '123')
        self.assertIn('qacct -j 123 || true', remote.call_args.args[0])
        self.assertIn('Completion/success unconfirmed', output)
        self.assertIn('maxvmem      1.000G', output)
        self.assertEqual(output.count('taskid'), 2)
        self.assertEqual(sum(s.startswith('=') for s in output.splitlines()), 2)
        self.assertNotIn('qname', output)
        self.assertNotIn('cpu', output)

    def test_status_full_and_missing_accounting(self):
        with patch.object(hpc.Remote, 'run', side_effect=self.fake_finished(self.QACCT)):
            self.assertIn('cpu          1.000', self.run_cli('status', '123', '--full'))
        with patch.object(hpc.Remote, 'run', side_effect=self.fake_finished('')):
            self.assertIn('No accounting record yet', self.run_cli('status', '123'))

    def test_queue_failure_does_not_claim_completion(self):
        with patch.object(hpc.Remote, 'run', side_effect=RuntimeError('SSH failed')):
            with self.assertRaises(RuntimeError):
                self.run_cli('status', '123')

    def test_collect_failure_does_not_create_output(self):
        out = self.root / 'new-output'
        with patch.object(hpc.Remote, 'run', side_effect=RuntimeError('missing results')):
            with self.assertRaises(RuntimeError):
                self.run_cli('collect', '--remote', '/shared/user/jobs/run', '--local', str(out))
        self.assertFalse(out.exists())

    def test_collect_extracts_remote_regular_files(self):
        def fake(command, **kw):
            with tarfile.open(fileobj=kw['stdout'], mode='w:gz') as tf:
                info = tarfile.TarInfo('results/output.txt')
                info.size = 2
                tf.addfile(info, io.BytesIO(b'ok'))
            return ''
        out = self.root / 'output'
        with patch.object(hpc.Remote, 'run', side_effect=fake):
            self.run_cli('collect', '--remote', '/shared/user/jobs/run', '--local', str(out))
        self.assertEqual((out / 'results' / 'output.txt').read_text(), 'ok')

    def test_unsafe_archives_are_rejected_before_extraction(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryFile() as archive:
                with tarfile.open(fileobj=archive, mode='w:gz') as tf:
                    item = tarfile.TarInfo(name)
                    item.type = kind
                    item.linkname = '../escape' if kind == tarfile.SYMTYPE else ''
                    tf.addfile(item)
                archive.seek(0)
                with self.assertRaises(ValueError):
                    hpc.safe_extract(archive, self.root / 'unsafe-output')
                self.assertFalse((self.root / 'unsafe-output').exists())

    def test_template_and_crlf_job_are_blocked(self):
        for data in (b'# CONFIGURE_BEFORE_SUBMIT\nexit 2\n', b'echo ok\r\n'):
            (self.local / 'job.sge').write_bytes(data)
            with patch.object(hpc.Remote, 'run') as remote, self.assertRaises(ValueError):
                self.run_cli(*self.transfer_args('submit'), '--job', 'job.sge', '--approved')
            remote.assert_not_called()

    def test_remote_paths_cannot_escape_configured_root(self):
        r = hpc.Remote(self.cfg)
        for value in ('/shared/user/jobs', '/shared/user/jobs-other/run', '/shared/user/jobs/../other'):
            with self.subTest(path=value), self.assertRaises(ValueError):
                r.directory(value)

    def test_ssh_argv_supports_key_path_spaces_and_preserves_host_verification(self):
        self.cfg.update(identity_file='C:/keys with spaces/key', sge_bin_dirs=['/opt/grid engine/bin'])
        with patch.object(hpc.shutil, 'which', return_value='ssh'), patch.object(hpc.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, b'ok\n', b'')
            output = hpc.Remote(self.cfg).run('id -un')
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index('-i') + 1], 'C:/keys with spaces/key')
        self.assertNotIn('StrictHostKeyChecking=no', ' '.join(argv))
        self.assertIn("'/opt/grid engine/bin'", argv[-1])
        self.assertEqual(output, 'ok\n')


if __name__ == '__main__':
    unittest.main()
