# run with: python3 -m unittest discover Tools/Scripts/tests

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
GIT_SD1 = SCRIPTS_DIRECTORY / 'git-sd1'
FAKE_REMOTE_URL = 'https://github.com/team/detector.git'


def load_git_sd1():
    loader = importlib.machinery.SourceFileLoader('git_sd1', str(GIT_SD1))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


git_sd1 = load_git_sd1()


class PullRequestTextTest(unittest.TestCase):
    def test_single_commit_uses_its_title_and_body(self):
        message = 'Detection: average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.\n\n* detection/fusion.py:\n'
        self.assertEqual(git_sd1.pull_request_text([message]),
                         ('Detection: average scores', 'Reviewed by NOBODY (OOPS!).\n\nWhy.\n\n* detection/fusion.py:'))

    def test_multiple_commits_get_a_section_each(self):
        title, body = git_sd1.pull_request_text(['First\n\nOne.', 'Second\n\nTwo.'])
        self.assertEqual(title, 'First')
        self.assertEqual(body, '#### First\n\nOne.\n\n#### Second\n\nTwo.')

    def test_reviewer_placeholder_is_allowed_but_others_are_not(self):
        message = '[Detection] Need a short description (OOPS!).\n\nReviewed by NOBODY (OOPS!).\n\nWhy.'
        self.assertEqual(git_sd1.unfinished_placeholders([message]), ['[Detection] Need a short description (OOPS!).'])

    def test_mentioning_the_marker_in_prose_is_not_a_placeholder(self):
        message = 'Title\n\nLines still\nmarked (OOPS!) block the pull request unless it\'s a draft.'
        self.assertEqual(git_sd1.unfinished_placeholders([message]), [])


class FakeGitHub(BaseHTTPRequestHandler):
    # class level so the test can inspect what git-sd1 sent
    requests = []
    pull_requests = []

    def respond(self, payload, status=200):
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_payload(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else None

    def do_GET(self):
        FakeGitHub.requests.append(('GET', self.path, None, self.headers.get('Authorization')))
        self.respond(FakeGitHub.pull_requests)

    def do_POST(self):
        payload = self.read_payload()
        FakeGitHub.requests.append(('POST', self.path, payload, self.headers.get('Authorization')))
        pull_request = {'number': 7, 'html_url': 'https://github.com/team/detector/pull/7', **payload}
        FakeGitHub.pull_requests.append(pull_request)
        self.respond(pull_request, status=201)

    def do_PATCH(self):
        payload = self.read_payload()
        FakeGitHub.requests.append(('PATCH', self.path, payload, self.headers.get('Authorization')))
        FakeGitHub.pull_requests[0].update(payload)
        self.respond(FakeGitHub.pull_requests[0])

    def log_message(self, *arguments):
        pass


class PullRequestEndToEndTest(unittest.TestCase):
    def setUp(self):
        FakeGitHub.requests = []
        FakeGitHub.pull_requests = []
        self.server = HTTPServer(('127.0.0.1', 0), FakeGitHub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.remote = root / 'remote.git'
        self.repository = root / 'clone'
        # editors like vs code set GIT_ASKPASS to hand git their own github login,
        # which would also bypass the missing-token path under test
        inherited = {name: value for name, value in os.environ.items()
                     if name not in ('GIT_ASKPASS', 'SSH_ASKPASS', 'GITHUB_TOKEN', 'GH_TOKEN')}
        self.environment = {
            **inherited,
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_EDITOR': 'true',
            'GIT_AUTHOR_NAME': 'tester', 'GIT_AUTHOR_EMAIL': 'tester@example.com',
            'GIT_COMMITTER_NAME': 'tester', 'GIT_COMMITTER_EMAIL': 'tester@example.com',
            'GITHUB_TOKEN': 'test-token',
            'SD1_GITHUB_API': f'http://127.0.0.1:{self.server.server_port}',
        }
        subprocess.run(['git', 'init', '--quiet', '--bare', '--initial-branch=main', str(self.remote)], check=True, env=self.environment)
        self.repository.mkdir()
        self.git('init', '--quiet', '--initial-branch=main')
        # origin keeps a github url, which is what git-sd1 reads owner/repo from, while
        # insteadOf quietly sends the actual fetches and pushes to the local bare repo
        self.git('remote', 'add', 'origin', FAKE_REMOTE_URL)
        self.git('config', f'url.{self.remote}.insteadOf', FAKE_REMOTE_URL)
        # apple's git has the keychain helper built in, which GIT_CONFIG_NOSYSTEM doesn't
        # turn off. an empty value clears the helper list so the developer's real
        # github token never reaches these tests
        self.git('config', 'credential.helper', '')
        (self.repository / 'README.md').write_text('detector\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'initial')
        self.git('push', '--quiet', 'origin', 'main')
        self.run_sd1('setup')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.repository, env=self.environment,
                              check=True, capture_output=True, text=True).stdout.strip()

    def run_sd1(self, *arguments, environment=None):
        return subprocess.run([sys.executable, str(GIT_SD1), *arguments], cwd=self.repository,
                              env=environment or self.environment, capture_output=True, text=True)

    def commit_with_message(self, message):
        self.git('commit', '--quiet', '-m', message)

    def test_from_main_creates_branch_pushes_and_opens_then_updates(self):
        (self.repository / 'fusion.py').write_text('def fuse(scores):\n    return max(scores)\n')
        self.git('add', '.')
        self.commit_with_message('Detection: add fusion\n\nReviewed by NOBODY (OOPS!).\n\nFuses scores.\n\n* fusion.py: Added.')

        result = self.run_sd1('pr')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('branch', '--show-current'), 'eng/detection-add-fusion')
        # main went back to matching origin so the next piece of work starts clean
        self.assertEqual(self.git('rev-parse', 'main'), self.git('rev-parse', 'origin/main'))
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'eng/detection-add-fusion'),
                         self.git('rev-parse', 'HEAD'))

        method, path, payload, authorization = FakeGitHub.requests[-1]
        self.assertEqual((method, path), ('POST', '/repos/team/detector/pulls'))
        self.assertEqual(payload['title'], 'Detection: add fusion')
        self.assertEqual(payload['head'], 'eng/detection-add-fusion')
        self.assertEqual(payload['base'], 'main')
        self.assertIn('* fusion.py: Added.', payload['body'])
        self.assertEqual(authorization, 'Bearer test-token')

        # review feedback: stage a fix and rerun, which folds it into the same commit
        (self.repository / 'fusion.py').write_text('def fuse(scores):\n    return sum(scores) / len(scores)\n')
        self.git('add', '.')
        result = self.run_sd1('pr')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('rev-list', '--count', 'origin/main..HEAD'), '1')
        self.assertEqual(FakeGitHub.requests[-1][:2], ('PATCH', '/repos/team/detector/pulls/7'))
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'eng/detection-add-fusion'),
                         self.git('rev-parse', 'HEAD'))

    def test_new_commit_from_staged_changes_on_main(self):
        (self.repository / 'thresholds.py').write_text('PAUSE = 0.8\n')
        self.git('add', '.')
        # the hook's template still has a title placeholder, so only a draft is allowed
        refused = self.run_sd1('pr')
        self.assertEqual(refused.returncode, 1)
        self.assertIn('Need a short description (OOPS!).', refused.stderr)
        self.assertEqual(FakeGitHub.requests, [])

        result = self.run_sd1('pr', '--draft')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(FakeGitHub.requests[-1][2]['draft'])
        self.assertIn('* thresholds.py: Added.', FakeGitHub.requests[-1][2]['body'])

    def test_nothing_to_open(self):
        result = self.run_sd1('pr')
        self.assertEqual(result.returncode, 1)
        self.assertIn('nothing to open a pull request for', result.stderr)

    def test_rebases_onto_new_work_on_main(self):
        self.git('switch', '--quiet', '-c', 'eng/mine')
        (self.repository / 'mine.py').write_text('x = 1\n')
        self.git('add', '.')
        self.commit_with_message('Mine\n\nReviewed by NOBODY (OOPS!).\n\nMine.\n\n* mine.py: Added.')

        # a teammate lands something on main in the meantime
        other = Path(self.temporary_directory.name) / 'other'
        subprocess.run(['git', 'clone', '--quiet', str(self.remote), str(other)], check=True, env=self.environment)
        (other / 'theirs.py').write_text('y = 2\n')
        subprocess.run(['git', 'add', '.'], cwd=other, check=True, env=self.environment)
        subprocess.run(['git', 'commit', '--quiet', '-m', 'theirs'], cwd=other, check=True, env=self.environment)
        subprocess.run(['git', 'push', '--quiet', 'origin', 'main'], cwd=other, check=True, env=self.environment)

        result = self.run_sd1('pr')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repository / 'theirs.py').exists())
        self.assertEqual(self.git('rev-list', '--count', 'origin/main..HEAD'), '1')

    def test_missing_token_still_pushes_and_explains(self):
        (self.repository / 'a.py').write_text('a = 1\n')
        self.git('add', '.')
        self.commit_with_message('Add a\n\nReviewed by NOBODY (OOPS!).\n\nA.\n\n* a.py: Added.')
        environment = {name: value for name, value in self.environment.items() if name not in ('GITHUB_TOKEN', 'GH_TOKEN')}
        result = self.run_sd1('pr', environment=environment)
        self.assertEqual(result.returncode, 1)
        self.assertIn('found no github token', result.stderr)
        self.assertEqual(self.git('--git-dir', str(self.remote), 'rev-parse', 'eng/add-a'), self.git('rev-parse', 'HEAD'))


if __name__ == '__main__':
    unittest.main()
