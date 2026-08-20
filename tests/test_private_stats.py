import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate_readme
import today


class PrivateRepositoryStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.original_cache_dir = today.CACHE_DIR
        self.original_user_name = today.USER_NAME
        today.CACHE_DIR = Path(self.temp_dir.name)
        today.USER_NAME = "Vikbg"
        self.addCleanup(setattr, today, "CACHE_DIR", self.original_cache_dir)
        self.addCleanup(setattr, today, "USER_NAME", self.original_user_name)

        self.original_private_commit_count = generate_readme._PRIVATE_COMMIT_COUNT
        generate_readme._PRIVATE_COMMIT_COUNT = 0
        self.addCleanup(
            setattr,
            generate_readme,
            "_PRIVATE_COMMIT_COUNT",
            self.original_private_commit_count,
        )

    def test_private_repository_stats_are_aggregated_without_entering_public_cache(self):
        public_repo = "Vikbg/public-repo"
        private_repo = "Vikbg/private-repo"
        edges = [
            {
                "node": {
                    "nameWithOwner": public_repo,
                    "isPrivate": False,
                    "defaultBranchRef": None,
                }
            },
            {
                "node": {
                    "nameWithOwner": private_repo,
                    "isPrivate": True,
                    "defaultBranchRef": {
                        "target": {"history": {"totalCount": 2}}
                    },
                }
            },
        ]
        graphql_payload = {
            "user": {
                "repositories": {
                    "edges": edges,
                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                }
            }
        }

        with mock.patch.object(
            today, "graphql_request", return_value=graphql_payload
        ) as graphql_request, mock.patch.object(
            generate_readme,
            "uncached_private_repo_loc",
            return_value=(25, 5, 2),
        ) as private_repo_loc:
            loc_data = generate_readme.private_safe_loc_query(
                ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
                comment_size=0,
                force_cache=True,
            )

        query = graphql_request.call_args.args[1]
        self.assertIn("isPrivate", query)

        cache_text = today.cache_file_path().read_text(encoding="utf-8")
        public_hash = hashlib.sha256(public_repo.encode("utf-8")).hexdigest()
        private_hash = hashlib.sha256(private_repo.encode("utf-8")).hexdigest()
        self.assertIn(public_hash, cache_text)
        self.assertNotIn(private_hash, cache_text)

        self.assertEqual(loc_data[:3], [25, 5, 20])
        self.assertFalse(loc_data[3])
        self.assertEqual(generate_readme._PRIVATE_COMMIT_COUNT, 2)
        private_repo_loc.assert_called_once_with("Vikbg", "private-repo")

    def test_commit_counter_adds_private_commits_to_public_cached_commits(self):
        generate_readme._PRIVATE_COMMIT_COUNT = 11
        with mock.patch.object(
            generate_readme, "_ORIGINAL_COMMIT_COUNTER", return_value=290
        ):
            self.assertEqual(generate_readme.actions_safe_commit_counter(7), 301)


if __name__ == "__main__":
    unittest.main()
