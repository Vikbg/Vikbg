import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate_readme
import today


class StatsIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.original_cache_dir = today.CACHE_DIR
        self.original_user_name = today.USER_NAME
        self.original_owner_id = today.OWNER_ID
        today.CACHE_DIR = Path(self.temp_dir.name)
        today.USER_NAME = "Vikbg"
        today.OWNER_ID = "owner-id"
        self.addCleanup(setattr, today, "CACHE_DIR", self.original_cache_dir)
        self.addCleanup(setattr, today, "USER_NAME", self.original_user_name)
        self.addCleanup(setattr, today, "OWNER_ID", self.original_owner_id)

        self.original_private_commit_count = generate_readme._PRIVATE_COMMIT_COUNT
        self.original_private_contributed = getattr(
            generate_readme, "_PRIVATE_CONTRIBUTED_REPO_COUNT", 0
        )
        generate_readme._PRIVATE_COMMIT_COUNT = 0
        generate_readme._PRIVATE_CONTRIBUTED_REPO_COUNT = 0
        self.addCleanup(
            setattr,
            generate_readme,
            "_PRIVATE_COMMIT_COUNT",
            self.original_private_commit_count,
        )
        self.addCleanup(
            setattr,
            generate_readme,
            "_PRIVATE_CONTRIBUTED_REPO_COUNT",
            self.original_private_contributed,
        )

    @staticmethod
    def _history(edges, has_next=False, cursor=None):
        return {
            "edges": edges,
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        }

    def test_profile_generator_commits_are_not_counted_as_user_work(self):
        history = self._history(
            [
                {
                    "node": {
                        "author": {
                            "name": "Vikbg/GitHub-Actions-Bot",
                            "user": {"id": "owner-id"},
                        },
                        "additions": 100,
                        "deletions": 20,
                    }
                },
                {
                    "node": {
                        "author": {
                            "name": "Viktor Serhiienko",
                            "user": {"id": "owner-id"},
                        },
                        "additions": 7,
                        "deletions": 2,
                    }
                },
            ]
        )
        counter = getattr(
            generate_readme,
            "actions_safe_public_loc_counter_one_repo",
            today.loc_counter_one_repo,
        )

        result = counter("Vikbg", "Vikbg", [], [], history, 0, 0, 0)

        self.assertEqual(result, (7, 2, 1))

    def test_legacy_generator_name_is_only_excluded_in_profile_repository(self):
        history = self._history(
            [
                {
                    "node": {
                        "author": {
                            "name": "Vikbg/GitHub-Actions-Bot",
                            "user": {"id": "owner-id"},
                        },
                        "additions": 4,
                        "deletions": 1,
                    }
                }
            ]
        )
        counter = getattr(
            generate_readme,
            "actions_safe_public_loc_counter_one_repo",
            today.loc_counter_one_repo,
        )

        result = counter("Vikbg", "another-repo", [], [], history, 0, 0, 0)

        self.assertEqual(result, (4, 1, 1))

    def test_public_history_query_is_filtered_by_github_user_id(self):
        payload = {
            "repository": {
                "defaultBranchRef": {
                    "target": {"history": self._history([])}
                }
            }
        }
        recursive_loc = getattr(
            generate_readme,
            "actions_safe_public_recursive_loc",
            today.recursive_loc,
        )

        with mock.patch.object(
            today, "graphql_request", return_value=payload
        ) as graphql_request:
            recursive_loc("Vikbg", "repo", [], [], 0, 0, 0, None)

        query = graphql_request.call_args.args[1]
        variables = graphql_request.call_args.args[2]
        self.assertIn("author: {id: $author_id}", query)
        self.assertEqual(variables["author_id"], "owner-id")

    def test_private_history_query_filters_by_author_and_paginates(self):
        first_page = {
            "repository": {
                "defaultBranchRef": {
                    "target": {
                        "history": self._history(
                            [
                                {
                                    "node": {
                                        "author": {"user": {"id": "owner-id"}},
                                        "additions": 10,
                                        "deletions": 1,
                                    }
                                }
                            ],
                            has_next=True,
                            cursor="next-page",
                        )
                    }
                }
            }
        }
        second_page = {
            "repository": {
                "defaultBranchRef": {
                    "target": {
                        "history": self._history(
                            [
                                {
                                    "node": {
                                        "author": {"user": {"id": "owner-id"}},
                                        "additions": 20,
                                        "deletions": 2,
                                    }
                                }
                            ]
                        )
                    }
                }
            }
        }

        with mock.patch.object(
            today, "graphql_request", side_effect=[first_page, second_page]
        ) as graphql_request:
            result = generate_readme.uncached_private_repo_loc("Vikbg", "private")

        first_query = graphql_request.call_args_list[0].args[1]
        first_variables = graphql_request.call_args_list[0].args[2]
        second_variables = graphql_request.call_args_list[1].args[2]
        self.assertIn("author: {id: $author_id}", first_query)
        self.assertEqual(first_variables["author_id"], "owner-id")
        self.assertEqual(second_variables["cursor"], "next-page")
        self.assertEqual(result, (30, 3, 2))

    def test_private_repository_probe_uses_author_filtered_commit_count(self):
        payload = {
            "user": {
                "repositories": {
                    "edges": [],
                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                }
            }
        }

        with mock.patch.object(
            today, "graphql_request", return_value=payload
        ) as graphql_request, mock.patch.object(
            today, "cache_builder", return_value=[0, 0, 0, True]
        ):
            generate_readme.private_safe_loc_query(
                ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
                comment_size=0,
            )

        query = graphql_request.call_args.args[1]
        variables = graphql_request.call_args.args[2]
        self.assertIn("history(author: {id: $author_id})", query)
        self.assertEqual(variables["author_id"], "owner-id")

    def test_contributed_repos_counts_only_repositories_with_user_commits(self):
        cache_file = today.cache_file_path()
        cache_file.write_text(
            (today.CACHE_COMMENT_LINE * today.COMMENT_BLOCK_SIZE)
            + "a 10 0 0 0\n"
            + "b 12 2 20 5\n"
            + "c 4 1 3 1\n",
            encoding="utf-8",
        )
        generate_readme._PRIVATE_CONTRIBUTED_REPO_COUNT = 2

        result = generate_readme.actions_safe_repo_stats(
            "repos", ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]
        )

        self.assertEqual(result, 4)

    def test_workflow_requires_private_token_and_stages_only_generated_outputs(self):
        workflow = Path(".github/workflows/build.yaml").read_text(encoding="utf-8")

        self.assertIn('ACCESS_TOKEN: ${{ secrets.ACCESS_TOKEN }}', workflow)
        self.assertNotIn("|| github.token", workflow)
        self.assertIn('git config --global user.name "github-actions[bot]"', workflow)
        self.assertIn(
            'git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"',
            workflow,
        )
        self.assertNotIn("git add .", workflow)
        self.assertIn(
            'git add -- dark_mode.svg light_mode.svg "$CACHE_FILE"', workflow
        )
        self.assertIn("git diff --cached --quiet", workflow)


if __name__ == "__main__":
    unittest.main()
