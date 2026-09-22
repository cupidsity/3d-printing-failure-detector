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
REPOSITORY_PATH = '/repos/team/detector'


def load_git_sd1():
    loader = importlib.machinery.SourceFileLoader('git_sd1', str(GIT_SD1))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


git_sd1 = load_git_sd1()


class ReviewerTest(unittest.TestCase):
    def test_reviewer_line_lists_names_like_a_sentence(self):
        self.assertEqual(git_sd1.reviewer_line([]), 'Unreviewed.')
        self.assertEqual(git_sd1.reviewer_line(['Caleb Feng']), 'Reviewed by Caleb Feng.')
        self.assertEqual(git_sd1.reviewer_line(['A', 'B']), 'Reviewed by A and B.')
        self.assertEqual(git_sd1.reviewer_line(['A', 'B', 'C']), 'Reviewed by A, B, and C.')

    def test_latest_review_per_person_wins_and_the_author_does_not_count(self):
        reviews = [
            {'user': {'login': 'caleb'}, 'state': 'CHANGES_REQUESTED'},
            {'user': {'login': 'caleb'}, 'state': 'COMMENTED'},
            {'user': {'login': 'caleb'}, 'state': 'APPROVED'},
            {'user': {'login': 'dana'}, 'state': 'APPROVED'},
            {'user': {'login': 'dana'}, 'state': 'DISMISSED'},
            {'user': {'login': 'author'}, 'state': 'APPROVED'},
            {'user': {'login': 'erin'}, 'state': 'CHANGES_REQUESTED'},
        ]
        self.assertEqual(git_sd1.review_outcome(reviews, 'author'), (['caleb'], ['erin']))

    def test_only_the_placeholder_is_replaced(self):
        message = 'Title\n\nReviewed by NOBODY (OOPS!).\n\nWhy.'
        self.assertEqual(git_sd1.with_reviewer(message, 'Reviewed by Caleb Feng.'), 'Title\n\nReviewed by Caleb Feng.\n\nWhy.')
        written = 'Title\n\nReviewed by Someone Else.\n\nWhy.'
        self.assertEqual(git_sd1.with_reviewer(written, 'Unreviewed.'), written)


class FakeGitHub(BaseHTTPRequestHandler):
    # class level so each test can set up the pull request and inspect the calls
    requests = []
    pull_request = {}
    reviews = []
    names = {}

    def respond(self, payload, status=200):
        encoded = json.dumps(payload).encode() if payload is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def record(self):
        length = int(self.headers.get('Content-Length', 0))
        payload = json.loads(self.rfile.read(length)) if length else None
        FakeGitHub.requests.append((self.command, self.path, payload))
        return payload

    def do_GET(self):
        self.record()
        if self.path == REPOSITORY_PATH:
            self.respond({'default_branch': 'main'})
        elif self.path == f'{REPOSITORY_PATH}/pulls/5':
            self.respond(FakeGitHub.pull_request)
        elif self.path.startswith(f'{REPOSITORY_PATH}/pulls/5/reviews'):
            self.respond(FakeGitHub.reviews)
        elif self.path.startswith('/users/'):
            login = self.path.rsplit('/', 1)[1]
            self.respond({'login': login, 'name': FakeGitHub.names.get(login)})
        else:
            self.respond({'message': 'Not Found'}, status=404)

    def do_POST(self):
        self.record()
        self.respond({'id': 1}, status=201)

    def do_PATCH(self):
        payload = self.record()
        FakeGitHub.pull_request.update(payload)
        self.respond(FakeGitHub.pull_request)

    def do_DELETE(self):
        self.record()
        self.respond(None, status=204)

    def log_message(self, *arguments):
        pass


class LandEndToEndTest(unittest.TestCase):
    def setUp(self):
        FakeGitHub.requests = []
        FakeGitHub.reviews = []
        FakeGitHub.names = {'caleb': 'Caleb Feng'}
        FakeGitHub.pull_request = {
            'number': 5, 'state': 'open', 'draft': False, 'merged': False,
            'user': {'login': 'author'},
            'base': {'ref': 'main'},
            'head': {'ref': 'eng/fusion', 'repo': {'full_name': 'team/detector'}},
        }
        self.server = HTTPServer(('127.0.0.1', 0), FakeGitHub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.remote = root / 'remote.git'
        self.repository = root / 'clone'
        inherited = {name: value for name, value in os.environ.items()
                     if name not in ('GIT_ASKPASS', 'SSH_ASKPASS', 'GITHUB_TOKEN', 'GH_TOKEN')}
        self.environment = {
            **inherited,
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_AUTHOR_NAME': 'author', 'GIT_AUTHOR_EMAIL': 'author@example.com',
            'GIT_COMMITTER_NAME': 'author', 'GIT_COMMITTER_EMAIL': 'author@example.com',
            'GITHUB_TOKEN': 'test-token',
            'SD1_GITHUB_API': f'http://127.0.0.1:{self.server.server_port}',
            'SD1_MERGED_POLL_SECONDS': '0',
        }
        subprocess.run(['git', 'init', '--quiet', '--bare', '--initial-branch=main', str(self.remote)], check=True, env=self.environment)
        self.repository.mkdir()
        self.git('init', '--quiet', '--initial-branch=main')
        # origin keeps a github url for git-sd1 to read owner/repo from, while
        # insteadOf sends the real fetches and pushes to the local bare repo
        self.git('remote', 'add', 'origin', FAKE_REMOTE_URL)
        self.git('config', f'url.{self.remote}.insteadOf', FAKE_REMOTE_URL)
        self.git('config', 'credential.helper', '')
        self.write('detection/fusion.py', 'def fuse(scores):\n    return max(scores)\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'initial')
        self.git('push', '--quiet', 'origin', 'main')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def git(self, *arguments, cwd=None):
        return subprocess.run(['git', *arguments], cwd=cwd or self.repository, env=self.environment,
                              check=True, capture_output=True, text=True).stdout.strip()

    def remote_git(self, *arguments):
        return self.git('--git-dir', str(self.remote), *arguments)

    def write(self, relative_path, content):
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def open_pull_request(self, message, content='def fuse(scores):\n    return sum(scores) / len(scores)\n'):
        # a branch with one commit, pushed the way `git-sd1 pr` would, plus the
        # refs/pull/5/head ref github keeps for every pull request
        self.git('switch', '--quiet', '-c', 'eng/fusion')
        self.write('detection/fusion.py', content)
        self.git('commit', '--quiet', '-am', message)
        self.git('push', '--quiet', 'origin', 'eng/fusion')
        self.remote_git('update-ref', 'refs/pull/5/head', self.git('rev-parse', 'HEAD'))

    def land(self):
        return subprocess.run([sys.executable, str(GIT_SD1), 'land', '5'], cwd=self.repository,
                              env=self.environment, capture_output=True, text=True)

    def comments(self):
        return [payload['body'] for method, path, payload in FakeGitHub.requests
                if method == 'POST' and path.endswith('/issues/5/comments')]

    def label_removed(self):
        return ('DELETE', f'{REPOSITORY_PATH}/issues/5/labels/merge-queue', None) in FakeGitHub.requests

    def test_approved_pull_request_lands_without_a_merge_commit(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.\n\n* detection/fusion.py:\n(fuse):')
        FakeGitHub.reviews = [{'user': {'login': 'caleb'}, 'state': 'APPROVED'}]

        result = self.land()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_git('rev-list', '--merges', 'main'), '')
        self.assertEqual(self.remote_git('rev-list', '--count', 'main'), '2')
        message = self.remote_git('log', '-1', '--format=%B', 'main')
        self.assertIn('Reviewed by Caleb Feng.', message)
        self.assertNotIn('OOPS', message)
        self.assertEqual(self.remote_git('log', '-1', '--format=%an', 'main'), 'author')
        # the pull request branch was moved to exactly what landed, so github can mark it merged
        self.assertEqual(self.remote_git('rev-parse', 'eng/fusion'), self.remote_git('rev-parse', 'main'))

        self.assertIn('Landed commit on `main`', self.comments()[-1])
        self.assertTrue(self.label_removed())
        self.assertEqual(FakeGitHub.pull_request['state'], 'closed')
        self.assertIn(('DELETE', f'{REPOSITORY_PATH}/git/refs/heads/eng/fusion', None), FakeGitHub.requests)
        # run by hand, it puts you back where you were
        self.assertEqual(self.git('branch', '--show-current'), 'eng/fusion')

    def test_no_approval_lands_as_unreviewed(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.')
        result = self.land()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\nUnreviewed.\n', self.remote_git('log', '-1', '--format=%B', 'main'))

    def test_requested_changes_block_landing(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.')
        FakeGitHub.reviews = [{'user': {'login': 'caleb'}, 'state': 'CHANGES_REQUESTED'}]
        before = self.remote_git('rev-parse', 'main')

        result = self.land()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.remote_git('rev-parse', 'main'), before)
        self.assertIn('changes were requested by @caleb', self.comments()[-1])
        self.assertTrue(self.label_removed())

    def test_unfinished_placeholders_block_landing(self):
        self.open_pull_request('[Detection] Need a short description (OOPS!).\n\nReviewed by NOBODY (OOPS!).\n\nWhy.')
        result = self.land()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Need a short description (OOPS!).', self.comments()[-1])

    def test_conflict_with_main_blocks_landing(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.')
        # a teammate lands a conflicting change first
        other = Path(self.temporary_directory.name) / 'other'
        subprocess.run(['git', 'clone', '--quiet', str(self.remote), str(other)], check=True, env=self.environment)
        (other / 'detection' / 'fusion.py').write_text('def fuse(scores):\n    return min(scores)\n')
        self.git('commit', '--quiet', '-am', 'theirs', cwd=other)
        self.git('push', '--quiet', 'origin', 'main', cwd=other)
        before = self.remote_git('rev-parse', 'main')

        result = self.land()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.remote_git('rev-parse', 'main'), before)
        self.assertIn('don\'t rebase cleanly', self.comments()[-1])
        self.assertEqual(self.git('branch', '--show-current'), 'eng/fusion')

    def test_hand_written_reviewer_is_kept(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by Dana Park.\n\nWhy.')
        FakeGitHub.reviews = [{'user': {'login': 'caleb'}, 'state': 'APPROVED'}]
        self.assertEqual(self.land().returncode, 0)
        self.assertIn('Reviewed by Dana Park.', self.remote_git('log', '-1', '--format=%B', 'main'))

    def test_uncommitted_changes_stop_a_local_run(self):
        self.open_pull_request('[Detection] Average scores\n\nReviewed by NOBODY (OOPS!).\n\nWhy.')
        self.write('detection/fusion.py', 'unsaved work\n')
        result = self.land()
        self.assertEqual(result.returncode, 1)
        self.assertIn('commit or stash', result.stderr)
        self.assertEqual((self.repository / 'detection' / 'fusion.py').read_text(), 'unsaved work\n')


if __name__ == '__main__':
    unittest.main()
