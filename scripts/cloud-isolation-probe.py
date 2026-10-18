"""Probe a non-gold canary boundary before any model worker is launched.

Run outside the command sandbox: bubblewrap itself establishes the restrictive
worker mount namespace. No oracle is generated, opened, or copied by this probe.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model-probe', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='bench0001-boundary-') as temporary:
        base = Path(temporary)
        canary = base / 'evaluator-canary'
        canary.write_text('PUBLIC NON-GOLD ISOLATION CANARY\n')
        worker = base / 'worker'
        worker.mkdir()
        (worker / 'home').mkdir()
        (worker / 'codex-home').mkdir()
        (worker / 'public.txt').write_text('allowed')
        # A native child has the coordinator UID and unrestricted read scope.
        direct = subprocess.run(['/usr/bin/python3', '-c',
            'import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text())',
            str(canary)], capture_output=True, text=True)
        command = ['bwrap', '--die-with-parent', '--new-session',
                   '--unshare-user', '--uid', '0', '--gid', '0',
                   '--unshare-pid', '--unshare-ipc', '--unshare-uts',
                   '--clearenv', '--ro-bind', '/usr', '/usr',
                   '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
                   '--symlink', 'usr/lib64', '/lib64',
                   '--ro-bind', '/opt/codex/bin', '/opt/codex/bin',
                   '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                   '--bind', str(worker), '/worker', '--chdir', '/worker',
                   '--setenv', 'PATH', '/opt/codex/bin:/usr/bin:/bin',
                   '--setenv', 'HOME', '/worker/home',
                   '--setenv', 'CODEX_HOME', '/worker/codex-home',
                   '--setenv', 'CODEX_NO_UPDATE', '1']
        for name in ('/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf'):
            if Path(name).exists():
                command += ['--ro-bind', name, name]
        # Preserve the managed proxy/CA path; never serialize environment values.
        for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy',
                     'https_proxy', 'no_proxy', 'SSL_CERT_FILE',
                     'REQUESTS_CA_BUNDLE', 'CODEX_SANDBOX_NETWORK_DISABLED'):
            if name in os.environ:
                command += ['--setenv', name, os.environ[name]]
        denied = [str(canary), str(repo), str(repo / 'benchkit/trusted_evaluator.py'),
                  str(repo / 'fixtures/private/oracle.jsonl'), '/run/docker.sock',
                  '/var/run/docker.sock', '/proc/1/root' + str(repo)]
        code = '''import json,pathlib,sys
denied=json.loads(sys.argv[1])
out={'allowed_read':pathlib.Path('/worker/public.txt').read_text()=='allowed','denied':{}}
for name in denied:
 try:
  p=pathlib.Path(name)
  list(p.iterdir()) if p.is_dir() else p.read_bytes()
  out['denied'][name]=False
 except (OSError,PermissionError): out['denied'][name]=True
print(json.dumps(out))
sys.exit(0 if out['allowed_read'] and all(out['denied'].values()) else 1)
'''
        check = subprocess.run(command + ['/usr/bin/python3', '-c', code,
                                          json.dumps(denied)], capture_output=True, text=True)
        report = {'native_same_uid_canary_readable': direct.returncode == 0,
                  'namespace_probe_exit_code': check.returncode,
                  'namespace_stdout': check.stdout, 'namespace_stderr': check.stderr,
                  'oracle_generated': False,
                  'native_isolation': 'ISOLATION_NOT_PROVEN',
                  'controlled_cli_isolation': 'PROVEN_FOR_TESTED_PATHS' if check.returncode == 0 else 'ISOLATION_NOT_PROVEN'}
        if check.returncode == 0:
            clean = subprocess.run(command + ['codex', 'login', 'status'], capture_output=True, text=True)
            report['fresh_home_login'] = {'exit_code': clean.returncode, 'stdout': clean.stdout, 'stderr': clean.stderr}
            auth = Path(os.environ['CODEX_HOME']) / 'auth.json'
            if auth.is_file():
                # Read-only selector for the existing built-in subscription. No
                # credential bytes are read by Python, copied, or logged.
                authenticated = command + ['--ro-bind', str(auth), '/worker/codex-home/auth.json']
                login = subprocess.run(authenticated + ['codex', 'login', 'status'], capture_output=True, text=True)
                report['managed_auth_login'] = {'exit_code': login.returncode, 'stdout': login.stdout, 'stderr': login.stderr}
                if args.model_probe:
                    start = time.monotonic()
                    with (args.out / 'luna-capability.jsonl').open('w') as events, (args.out / 'luna-capability.stderr').open('w') as errors:
                        try:
                            result = subprocess.run(authenticated + ['codex', '--no-daemon', 'exec',
                                '--ignore-user-config', '--ignore-rules', '--ephemeral',
                                '--skip-git-repo-check', '--json', '-m', 'gpt-6-luna',
                                '-c', 'model_reasoning_effort="medium"',
                                'Reply exactly CAPABILITY_OK. Do not call tools.'],
                                stdout=events, stderr=errors, timeout=45)
                            report['model_probe_exit_code'] = result.returncode
                        except subprocess.TimeoutExpired:
                            report['model_probe_exit_code'] = None
                            report['model_probe_timeout_seconds'] = 45
                    report['model_probe_elapsed_seconds'] = time.monotonic() - start
        (args.out / 'isolation.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
