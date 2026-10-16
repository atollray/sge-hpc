#!/usr/bin/env python3
"""Portable SGE helper. Local: Python >=3.12 + OpenSSH. Remote: POSIX + tar + SGE."""
import argparse
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile


DEFAULT_EXCLUDES = (
    '.git', '.ssh', '.env', '.env.*', '*.pem', '*.key', 'id_rsa*',
    'id_ed25519*', '__pycache__', '.venv', 'data', 'logs', 'results',
    'hpc-config.json',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative_path(value):
    p = PurePosixPath(value)
    require(value and not p.is_absolute() and '..' not in p.parts
            and '\\' not in value and not value.startswith('-')
            and str(p) != '.', 'Expected a relative path without ..: ' + value)
    return str(p)


def absolute_path(value):
    require(isinstance(value, str) and value.startswith('/')
            and value != '/' and '..' not in PurePosixPath(value).parts
            and not any(c in value for c in '\n\r\x00'),
            'Expected a non-root absolute POSIX path: ' + str(value))
    return str(PurePosixPath(value))


def load_config(path):
    cfg = json.loads(Path(path).expanduser().read_text(encoding='utf-8-sig'))
    require(isinstance(cfg, dict), 'Configuration must be a JSON object')
    target = cfg.get('target', '')
    require(isinstance(target, str) and bool(re.fullmatch(r'[\w.@:\[\]-]+', target))
            and not target.startswith('-'), 'Set target to your SSH alias or user@host')
    cfg['shared_root'] = absolute_path(cfg.get('shared_root', ''))
    for key in ('sge_bin_dirs', 'exclude'):
        cfg.setdefault(key, [])
        require(isinstance(cfg[key], list) and all(isinstance(s, str) for s in cfg[key]),
                key + ' must be an array of strings')
    cfg['sge_bin_dirs'] = [absolute_path(p) for p in cfg['sge_bin_dirs']]
    identity = cfg.get('identity_file', '')
    require(isinstance(identity, str), 'identity_file must be a string')
    if identity:
        cfg['identity_file'] = str(Path(identity).expanduser().resolve())
        require(Path(cfg['identity_file']).is_file(), 'SSH identity file not found')
    limit = cfg.setdefault('max_upload_mb', 100)
    require(isinstance(limit, (int, float)) and 0 < limit < float('inf'),
            'max_upload_mb must be a positive finite number')
    return cfg


class Remote:
    def __init__(self, cfg):
        self.cfg = cfg

    def run(self, command, *, stdin=None, stdout=None):
        require(shutil.which('ssh'), 'OpenSSH ssh executable not found')
        args = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15']
        if self.cfg.get('identity_file'):
            args += ['-i', self.cfg['identity_file']]
        prefix = ''
        if self.cfg['sge_bin_dirs']:
            prefix = 'export PATH=' + shlex.quote(':'.join(self.cfg['sge_bin_dirs'])) + ':"$PATH"; '
        args += [self.cfg['target'], prefix + command]
        result = subprocess.run(args, stdin=stdin, stdout=stdout or subprocess.PIPE,
                                stderr=subprocess.PIPE)
        error = result.stderr.decode('utf-8', errors='replace').strip()
        if result.returncode:
            raise RuntimeError(f'SSH/remote command failed ({result.returncode}): {error}')
        if error:
            print(error, file=sys.stderr)
        return result.stdout.decode('utf-8', errors='replace') if stdout is None else ''

    def directory(self, value):
        path = absolute_path(value)
        root = self.cfg['shared_root']
        require(path.startswith(root + '/'), '--remote must be below shared_root, not the root itself')
        return path

    def enter(self, path, create=False):
        # Resolve both paths remotely to reject symlinks escaping the shared root.
        root = shlex.quote(self.cfg['shared_root'])
        dest = shlex.quote(path)
        return (
            f'root=$(cd {root} && pwd -P) && '
            + (f'mkdir -p {dest} && ' if create else '')
            + f'cd {dest} && actual=$(pwd -P) && '
            'case "$actual" in "$root"/*) ;; *) echo "Path escapes shared_root" >&2; exit 2;; esac && '
        )


def upload_files(local, excludes, limit):
    require(local.is_dir(), 'Local directory not found: ' + str(local))
    files = []
    for folder, dirs, names in os.walk(local, followlinks=False):
        base = Path(folder)

        def excluded(path):
            rel = path.relative_to(local)
            return any(fnmatch.fnmatchcase(rel.as_posix(), pat)
                       or any(fnmatch.fnmatchcase(part, pat) for part in rel.parts)
                       for pat in excludes)

        dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink() and not excluded(base / d))
        for name in sorted(names):
            p = base / name
            if not p.is_symlink() and not excluded(p) and p.is_file():
                files.append(p)
    total = sum(p.stat().st_size for p in files)
    require(total <= limit * 1024 * 1024,
            f'Upload is {total / 1024 / 1024:.2f} MiB; exceeds max_upload_mb={limit}')
    require(files, 'No files selected for upload')
    return files, total


def upload(remote, local, dest, files):
    # Archive locally first: size/selection errors cannot partially upload files.
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode='w:gz') as tf:
            for p in files:
                tf.add(p, arcname=p.relative_to(local).as_posix(), recursive=False)
        archive.seek(0)
        remote.run(remote.enter(dest, create=True) + 'tar -xzf -', stdin=archive)


def safe_extract(archive, local):
    with tarfile.open(fileobj=archive, mode='r:gz') as tf:
        members = tf.getmembers()
        # Prevalidate all members before touching the output directory.
        require(all(m.isfile() or m.isdir() for m in members),
                'Result archive contains links or special files; collect regular files only')
        for m in members:
            require(not PurePosixPath(m.name).is_absolute()
                    and '..' not in PurePosixPath(m.name).parts and '\\' not in m.name,
                    'Unsafe archive member: ' + m.name)
        local.mkdir(parents=True, exist_ok=True)
        for m in members:
            tarfile.data_filter(m, str(local))
        tf.extractall(local, members=members, filter='data')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', help='Path to your private configuration JSON (not needed for doctor)')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('doctor', help='Check local tools without configuration, network access or writes')
    sub.add_parser('preflight', help='Check SSH, SGE commands and shared root')
    for action in ('sync', 'submit'):
        q = sub.add_parser(action)
        q.add_argument('--local', required=True)
        q.add_argument('--remote', required=True, help='Absolute path below shared_root')
        q.add_argument('--exclude', action='append', default=[])
        q.add_argument('--dry-run', action='store_true', help='Plan only; no SSH or writes')
        if action == 'submit':
            q.add_argument('--job', required=True, help='Job script relative to local directory')
            q.add_argument('--approved', action='store_true', help='Submission plan was authorized')
    q = sub.add_parser('status')
    q.add_argument('job_id')
    q = sub.add_parser('collect')
    q.add_argument('--remote', required=True)
    q.add_argument('--local', required=True)
    q.add_argument('--paths', nargs='+', default=['logs', 'results'])
    q.add_argument('--dry-run', action='store_true')
    return p


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    require(sys.version_info >= (3, 12), 'Python 3.12 or newer is required')
    if args.action == 'doctor':
        print('Python: ' + sys.version.split()[0])
        print('Interpreter: ' + sys.executable)
        for name in ('ssh', 'ssh-keygen', 'ssh-add'):
            location = shutil.which(name)
            print(f'{name}: {location or "NOT FOUND"}')
        require(shutil.which('ssh'), 'OpenSSH client not found; see references/setup.md')
        print('Local check complete. No network connection, key inspection or configuration changes.')
        return
    if not args.config:
        cli.error('--config is required for ' + args.action + '; use doctor for a local-only check')
    cfg = load_config(args.config)
    remote = Remote(cfg)
    if args.action == 'preflight':
        command = (
            'set -e; printf "Host: "; hostname; printf "User: "; id -un; '
            'missing=0; for c in qsub qstat qacct tar; do '
            'if command -v "$c" >/dev/null 2>&1; then printf "OK: %s\\n" "$c"; '
            'else printf "MISSING: %s (check login host and SGE PATH)\\n" "$c" >&2; missing=1; fi; '
            'done; test "$missing" -eq 0 || exit 2; '
            f'cd {shlex.quote(cfg["shared_root"])} || '
            '{ echo "Shared root unavailable: check path and permissions" >&2; exit 2; }; '
            'test -w . || { echo "Shared root is not writable" >&2; exit 2; }; '
            'printf "Shared root (verify across compute nodes): "; pwd -P'
        )
        print(remote.run(command), end='')
        return
    if args.action == 'status':
        require(bool(re.fullmatch(r'[1-9][0-9]*', args.job_id)), 'Expected a positive numeric job ID')
        # Query the authenticated remote user, not the SSH alias string.
        queue = remote.run('qstat -u "$(id -un)"')
        lines = [s for s in queue.splitlines() if s.split() and s.split()[0] == args.job_id]
        if lines:
            print('\n'.join(lines))
            if any(len(s.split()) >= 5 and re.search('[Ee]', s.split()[4]) for s in lines):
                print(remote.run('qstat -j ' + args.job_id), end='')
        else:
            print('Not in queue. Completion/success unconfirmed; match accounting and logs to this run.')
            print(remote.run('qacct -j ' + args.job_id), end='')
        return
    dest = remote.directory(args.remote)
    local = Path(args.local).expanduser().resolve()
    print(f'{args.action}: {local} <-> {cfg["target"]}:{dest}')
    if args.action in ('sync', 'submit'):
        files, total = upload_files(local, DEFAULT_EXCLUDES + tuple(cfg['exclude'])
                                    + tuple(args.exclude), cfg['max_upload_mb'])
        print(f'Upload: {len(files)} files, {total / 1024 / 1024:.2f} MiB; no remote deletion')
        for f in files:
            print('  ' + f.relative_to(local).as_posix())
        if args.action == 'submit':
            job = relative_path(args.job)
            job_path = local / job
            require(job_path in files, 'Job file missing or excluded from upload')
            content = job_path.read_text(encoding='utf-8-sig')
            require('\r' not in job_path.read_bytes().decode('utf-8-sig'),
                    'Job script must use LF line endings')
            require('CONFIGURE_BEFORE_SUBMIT' not in content, 'Configure the job template first')
            print('Job script:\n' + content)
            require(args.dry_run or args.approved, 'Show --dry-run plan and obtain approval; then use --approved')
        if args.dry_run:
            print('Dry run: no connection, upload or submission.')
            return
        upload(remote, local, dest, files)
        if args.action == 'submit':
            out = remote.run(remote.enter(dest) + 'mkdir -p logs && qsub -terse ' + shlex.quote(job))
            print(out, end='')
            match = re.fullmatch(r'\s*([0-9]+)(?:\.[0-9,:-]+)?\s*', out)
            require(match, 'qsub response ambiguous; check qstat before any retry (job may already exist)')
            print('JOBID=' + match.group(1))
    elif args.action == 'collect':
        paths = [relative_path(v) for v in args.paths]
        print('Collect: ' + ', '.join(paths))
        if args.dry_run:
            print('Dry run: no connection or local writes.')
            return
        with tempfile.TemporaryFile() as archive:
            remote.run(remote.enter(dest) + 'tar -czf - -- ' + shlex.join(paths), stdout=archive)
            archive.seek(0)
            safe_extract(archive, local)
        print('Collection complete.')


if __name__ == '__main__':
    try:
        require(sys.version_info >= (3, 12), 'Python 3.12 or newer is required')
        main()
    except (ValueError, OSError, RuntimeError, tarfile.TarError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
