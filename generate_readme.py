"""Run the profile README generator with GitHub Actions-safe statistics.

GitHub's built-in ``GITHUB_TOKEN`` is scoped to the current repository. It can
resolve a user's repository connection but cannot read nested fields, such as
stargazer counts, from the user's other repositories. Public owner repository
statistics are therefore fetched through GitHub's public REST endpoint.

When ``ACCESS_TOKEN`` can read private repositories, private commit and LOC
statistics are aggregated in memory. Only public repositories are written to
the persistent repository cache, so private repository names, hashes, commit
counts, and per-repository LOC never enter the public Git history.
"""

import requests

import today

PUBLIC_REPOSITORIES_URL = "https://api.github.com/users/{username}/repos"
PUBLIC_PAGE_SIZE = 100
_PUBLIC_STATS_CACHE = None
_PRIVATE_COMMIT_COUNT = 0
_ORIGINAL_COMMIT_COUNTER = today.commit_counter


def public_repository_stats(username):
    """Return public owner repository and star totals using the REST API."""
    global _PUBLIC_STATS_CACHE

    if _PUBLIC_STATS_CACHE is not None:
        return _PUBLIC_STATS_CACHE

    repository_count = 0
    star_count = 0
    page = 1

    while True:
        response = requests.get(
            PUBLIC_REPOSITORIES_URL.format(username=username),
            params={
                "type": "owner",
                "sort": "full_name",
                "direction": "asc",
                "per_page": PUBLIC_PAGE_SIZE,
                "page": page,
            },
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Vikbg-profile-readme",
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "public_repository_stats failed with status "
                f"{response.status_code}: {response.text}"
            )

        repositories = response.json()
        if not isinstance(repositories, list):
            raise RuntimeError(
                "public_repository_stats returned an unexpected response: "
                f"{repositories}"
            )

        repository_count += len(repositories)
        star_count += sum(
            int(repository.get("stargazers_count", 0))
            for repository in repositories
        )

        if len(repositories) < PUBLIC_PAGE_SIZE:
            break
        page += 1

    _PUBLIC_STATS_CACHE = {
        "repos": repository_count,
        "stars": star_count,
    }
    return _PUBLIC_STATS_CACHE


def repository_connection_count(owner_affiliation):
    """Count repositories without requesting fields blocked for integrations."""
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!) {
        user(login: $login) {
            repositories(ownerAffiliations: $owner_affiliation) {
                totalCount
            }
        }
    }"""
    data = today.graphql_request(
        "repository_connection_count",
        query,
        {
            "owner_affiliation": owner_affiliation,
            "login": today.USER_NAME,
        },
    )
    return int(data["user"]["repositories"]["totalCount"])


def actions_safe_repo_stats(count_type, owner_affiliation):
    """Replacement for today.graph_repos_stars that works with GITHUB_TOKEN."""
    today.query_count("graph_repos_stars")
    affiliations = list(owner_affiliation)

    if affiliations == ["OWNER"]:
        return public_repository_stats(today.USER_NAME).get(count_type, 0)
    if count_type == "repos":
        return repository_connection_count(affiliations)
    return 0


def uncached_private_repo_loc(
    owner,
    repo_name,
    cursor=None,
    addition_total=0,
    deletion_total=0,
    my_commits=0,
):
    """Count one private repository without persisting repository metadata."""
    today.query_count("recursive_loc")
    query = """
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            edges {
                                node {
                                    ... on Commit {
                                        author {
                                            user {
                                                id
                                            }
                                        }
                                        deletions
                                        additions
                                    }
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }"""
    data = today.graphql_request(
        "uncached_private_repo_loc",
        query,
        {"repo_name": repo_name, "owner": owner, "cursor": cursor},
    )
    repository = data.get("repository")
    if repository is None:
        return addition_total, deletion_total, my_commits

    branch = repository.get("defaultBranchRef")
    if branch is None:
        return addition_total, deletion_total, my_commits

    history = branch["target"]["history"]
    for edge in history["edges"]:
        commit = edge["node"]
        author = commit.get("author") or {}
        user = author.get("user") or {}
        if user.get("id") == today.OWNER_ID:
            my_commits += 1
            addition_total += commit["additions"]
            deletion_total += commit["deletions"]

    if not history["pageInfo"]["hasNextPage"]:
        return addition_total, deletion_total, my_commits

    return uncached_private_repo_loc(
        owner,
        repo_name,
        history["pageInfo"]["endCursor"],
        addition_total,
        deletion_total,
        my_commits,
    )


def private_safe_loc_query(owner_affiliation, comment_size=0, force_cache=False):
    """Aggregate public cached stats plus private in-memory stats."""
    global _PRIVATE_COMMIT_COUNT
    _PRIVATE_COMMIT_COUNT = 0

    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            isPrivate
                            defaultBranchRef {
                                target {
                                    ... on Commit {
                                        history {
                                            totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }"""

    cursor = None
    edges = []
    while True:
        today.query_count("loc_query")
        data = today.graphql_request(
            "private_safe_loc_query",
            query,
            {
                "owner_affiliation": owner_affiliation,
                "login": today.USER_NAME,
                "cursor": cursor,
            },
        )
        repositories = data["user"]["repositories"]
        edges.extend(repositories["edges"])

        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    public_edges = [
        edge for edge in edges if not edge["node"].get("isPrivate", False)
    ]
    private_edges = [
        edge for edge in edges if edge["node"].get("isPrivate", False)
    ]

    public_loc = today.cache_builder(public_edges, comment_size, force_cache)
    private_additions = 0
    private_deletions = 0

    for edge in private_edges:
        node = edge["node"]
        branch = node.get("defaultBranchRef")
        history = None if branch is None else branch["target"]["history"]
        if history is None or int(history["totalCount"]) == 0:
            continue

        owner, repo_name = node["nameWithOwner"].split("/", 1)
        additions, deletions, commits = uncached_private_repo_loc(owner, repo_name)
        private_additions += additions
        private_deletions += deletions
        _PRIVATE_COMMIT_COUNT += commits

    return [
        public_loc[0] + private_additions,
        public_loc[1] + private_deletions,
        public_loc[2] + private_additions - private_deletions,
        public_loc[3],
    ]


def actions_safe_commit_counter(comment_size):
    """Add in-memory private commits to the public cached commit total."""
    return _ORIGINAL_COMMIT_COUNTER(comment_size) + _PRIVATE_COMMIT_COUNT


def main():
    today.graph_repos_stars = actions_safe_repo_stats
    today.loc_query = private_safe_loc_query
    today.commit_counter = actions_safe_commit_counter
    today.main()


if __name__ == "__main__":
    main()
