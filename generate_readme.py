"""Run the profile README generator with GitHub Actions-safe public statistics.

GitHub's built-in ``GITHUB_TOKEN`` is scoped to the current repository. It can
resolve a user's repository connection but cannot read nested fields, such as
stargazer counts, from the user's other repositories. Public owner repository
statistics are therefore fetched through GitHub's public REST endpoint, while
the existing authenticated GraphQL logic remains available for the rest of the
generator.
"""

import requests

import today

PUBLIC_REPOSITORIES_URL = "https://api.github.com/users/{username}/repos"
PUBLIC_PAGE_SIZE = 100
_PUBLIC_STATS_CACHE = None


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


def main():
    today.graph_repos_stars = actions_safe_repo_stats
    today.main()


if __name__ == "__main__":
    main()
