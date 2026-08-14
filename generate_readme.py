"""Run the profile README generator with GitHub Actions-safe public statistics.

GitHub's built-in ``GITHUB_TOKEN`` is scoped to the current repository. It can
resolve a user's repository connection but cannot read nested fields, such as
stargazer counts, from the user's other repositories. Public owner repository
statistics are therefore fetched through GitHub's public REST endpoint, while
the existing authenticated GraphQL logic remains available for the rest of the
generator.
"""

import requests
from lxml.etree import parse

import today

PUBLIC_REPOSITORIES_URL = "https://api.github.com/users/{username}/repos"
PUBLIC_PAGE_SIZE = 100
_PUBLIC_STATS_CACHE = None
_ORIGINAL_JUSTIFY_FORMAT = today.justify_format
_ORIGINAL_SVG_OVERWRITE = today.svg_overwrite


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


def readme_justify_format(root, element_id, new_text, length=0):
    """Keep LOC dot padding before the total, never before the deletion value."""
    if element_id == "loc_del":
        today.find_and_replace(root, element_id, today.format_display_text(new_text))
        today.find_and_replace(root, "loc_del_dots", "")
        return
    _ORIGINAL_JUSTIFY_FORMAT(root, element_id, new_text, length)


def stats_row_width(commit_data, follower_data):
    """Return the rendered character width of the commits/followers stats row."""
    commit_text = today.format_display_text(commit_data)
    follower_text = today.format_display_text(follower_data)
    return len(
        f". Commits:{today.build_dot_string(commit_text, today.COMMIT_DATA_WIDTH)}"
        f"{commit_text}"
        f"{today.secondary_stat_gap(today.commit_stats_left_width(commit_data))}"
        f"Followers:{today.build_dot_string(follower_text, today.FOLLOWER_DATA_WIDTH)}"
        f"{follower_text}"
    )


def loc_dot_padding(width):
    """Build a dot leader of exactly ``width`` characters."""
    if width <= 0:
        return ""
    if width == 1:
        return " "
    if width == 2:
        return ". "
    return " " + ("." * (width - 2)) + " "


def readme_svg_overwrite(
    filename,
    age_data,
    commit_data,
    star_data,
    repo_data,
    contrib_data,
    follower_data,
    loc_data,
):
    """Render an SVG and align the final LOC parenthesis with the stats rows."""
    _ORIGINAL_SVG_OVERWRITE(
        filename,
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        loc_data,
    )

    loc_text = today.format_display_text(loc_data[2])
    added_text = today.format_compact_number(loc_data[0])
    deleted_text = today.format_compact_number(loc_data[1])

    target_width = stats_row_width(commit_data, follower_data)
    fixed_width = len(
        f". GitHub LOC:{loc_text} ( +{added_text}, -{deleted_text} )"
    )
    padding_width = max(1, target_width - fixed_width)

    tree = parse(filename)
    root = tree.getroot()
    today.find_and_replace(root, "loc_data_dots", loc_dot_padding(padding_width))
    today.find_and_replace(root, "loc_del_dots", "")
    tree.write(filename, encoding="utf-8", xml_declaration=True)


def main():
    today.graph_repos_stars = actions_safe_repo_stats
    today.justify_format = readme_justify_format
    today.svg_overwrite = readme_svg_overwrite
    today.main()


if __name__ == "__main__":
    main()
