"""Copyright 2026 Vikbg.

SPDX-License-Identifier: Apache-2.0
Keep the attribution notice from the repository NOTICE file when redistributing.
"""

import datetime
import hashlib
import os
import re
import time
from pathlib import Path

import requests
from dateutil import relativedelta
from dotenv import load_dotenv
from lxml.etree import parse

load_dotenv()

# GitHub API and local file layout used by the script.
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
CACHE_DIR = Path("cache")
ARCHIVE_PATH = CACHE_DIR / "repository_archive.txt"
SVG_FILES = ("dark_mode.svg", "light_mode.svg")

# Fixed values that shape the generated README content.
COMMENT_BLOCK_SIZE = 7
BIRTHDAY = datetime.datetime(2010, 10, 1)
ARCHIVE_USER_ID = "U_kgDOC15JXw"
CACHE_COMMENT_LINE = "This line is a comment block. Write whatever you want here.\n"

# Shared visible widths used by the profile card alignment engine.
PROFILE_ROW_WIDTH = 60
STATS_LEFT_COLUMN_WIDTH = 34
STATS_SEPARATOR = " |  "

# Simple rows share one renderer so changing a value never requires recounting dots manually.
SIMPLE_ROW_SPECS = (
    ("os_dots", "os_value", ". OS:"),
    ("age_data_dots", "age_data", ". Uptime:"),
    ("host_dots", "host_value", ". Host:"),
    ("kernel_dots", "kernel_value", ". Kernel:"),
    ("ide_dots", "ide_value", ". IDE:"),
    (
        "languages_application_dots",
        "languages_application_value",
        ". Languages.Application:",
    ),
    ("languages_systems_dots", "languages_systems_value", ". Languages.Systems:"),
    ("languages_spoken_dots", "languages_spoken_value", ". Languages.Spoken:"),
    ("hobbies_software_dots", "hobbies_software_value", ". Hobbies.Software:"),
    ("hobbies_hardware_dots", "hobbies_hardware_value", ". Hobbies.Hardware:"),
    ("hobbies_science_dots", "hobbies_science_value", ". Hobbies.Science:"),
    ("portfolio_dots", "portfolio_value", ". Portfolio.Link:"),
    ("email_dots", "email_value", ". Email.Work:"),
    ("instagram_dots", "instagram_value", ". Instagram:"),
    ("discord_dots", "discord_value", ". Discord:"),
)

# Simple runtime counters so the script can report how many GraphQL calls each path used.
QUERY_COUNT = {
    "user_getter": 0,
    "follower_getter": 0,
    "graph_repos_stars": 0,
    "recursive_loc": 0,
    "loc_query": 0,
}

# Runtime state is populated after environment configuration and user lookup.
HEADERS = {}
USER_NAME = ""
OWNER_ID = None


# Read one required environment variable and fail early with a precise message if it is missing.
def require_env(name):
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


# Build the authorization header and target GitHub username used by all later API calls.
def configure_environment():
    global HEADERS, USER_NAME
    access_token = require_env("ACCESS_TOKEN")
    USER_NAME = require_env("USER_NAME")
    HEADERS = {"authorization": f"token {access_token}"}


# Derive the per-user cache filename from the GitHub login so different users do not share cache data.
def cache_file_path():
    hashed_user = hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{hashed_user}.txt"


# Convert the configured birthday into a human-readable uptime string for the SVG card.
def format_age(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    parts = [
        f"{diff.years} year{format_plural(diff.years)}",
        f"{diff.months} month{format_plural(diff.months)}",
        f"{diff.days} day{format_plural(diff.days)}",
    ]
    suffix = " 🎂" if diff.months == 0 and diff.days == 0 else ""
    return ", ".join(parts) + suffix


# Return the plural suffix used by the age formatter.
def format_plural(value):
    return "s" if value != 1 else ""


# Turn an HTTP error into a readable exception that includes the current query counters.
def raise_request_error(operation_name, response):
    if response.status_code == 403:
        raise RuntimeError(
            "Too many requests in a short amount of time. GitHub returned 403."
        )
    raise RuntimeError(
        f"{operation_name} failed with status {response.status_code}: "
        f"{response.text}. Query counts: {QUERY_COUNT}"
    )


# Send one GraphQL request and normalize all failure cases in one place.
# If a cache write is in progress, partial_cache lets us persist whatever was computed before raising.
def graphql_request(operation_name, query, variables, partial_cache=None):
    try:
        response = requests.post(
            GITHUB_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException as error:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} request failed: {error}") from error

    # Non-200 responses are handled before trying to parse the body as GraphQL JSON.
    if response.status_code != 200:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise_request_error(operation_name, response)

    # GitHub can still return malformed data, so JSON parsing gets its own guarded error path.
    try:
        payload = response.json()
    except ValueError as error:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(
            f"{operation_name} returned invalid JSON: {response.text}"
        ) from error

    # GraphQL-level errors still arrive inside a 200 response, so check them explicitly.
    if payload.get("errors"):
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(
            f"{operation_name} returned GraphQL errors: {payload['errors']}"
        )

    return payload["data"]


# Count either repositories or stars across all pages of a repository connection.
# count_type controls which final aggregate is returned to the caller.
def graph_repos_stars(count_type, owner_affiliation):
    total_repositories = 0
    total_stars = 0
    cursor = None

    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            stargazers {
                                totalCount
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

    while True:
        query_count("graph_repos_stars")
        variables = {
            "owner_affiliation": owner_affiliation,
            "login": USER_NAME,
            "cursor": cursor,
        }
        data = graphql_request("graph_repos_stars", query, variables)
        repositories = data["user"]["repositories"]

        # totalCount is the connection-wide total, while stars must be accumulated page by page.
        total_repositories = repositories["totalCount"]
        total_stars += stars_counter(repositories["edges"])

        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    if count_type == "repos":
        return total_repositories
    if count_type == "stars":
        return total_stars
    return 0


# Traverse commit history for one repository, 100 commits at a time, until there are no more pages.
# The cache lists are passed through so partial results can still be saved if a request fails midway.
def recursive_loc(
    owner,
    repo_name,
    cache_rows,
    cache_header,
    addition_total=0,
    deletion_total=0,
    my_commits=0,
    cursor=None,
):
    query_count("recursive_loc")
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
    variables = {"repo_name": repo_name, "owner": owner, "cursor": cursor}
    data = graphql_request(
        "recursive_loc",
        query,
        variables,
        partial_cache=(cache_rows, cache_header),
    )
    branch = data["repository"]["defaultBranchRef"]

    # Empty repositories do not have a default branch, so they contribute nothing here.
    if branch is None:
        return 0, 0, 0

    history = branch["target"]["history"]
    return loc_counter_one_repo(
        owner,
        repo_name,
        cache_rows,
        cache_header,
        history,
        addition_total,
        deletion_total,
        my_commits,
    )


# Consume one page of commit history for a single repository.
# Only commits authored by the current GitHub user count toward the stored LOC totals.
def loc_counter_one_repo(
    owner,
    repo_name,
    cache_rows,
    cache_header,
    history,
    addition_total,
    deletion_total,
    my_commits,
):
    for edge in history["edges"]:
        author = edge["node"].get("author") or {}
        user = author.get("user") or {}

        # GitHub can return commits without a mapped user, so guard against missing author identities.
        if user.get("id") == OWNER_ID:
            my_commits += 1
            addition_total += edge["node"]["additions"]
            deletion_total += edge["node"]["deletions"]

    if not history["pageInfo"]["hasNextPage"]:
        return addition_total, deletion_total, my_commits

    # Recurse with the accumulated totals until the full repository history has been processed.
    return recursive_loc(
        owner,
        repo_name,
        cache_rows,
        cache_header,
        addition_total,
        deletion_total,
        my_commits,
        history["pageInfo"]["endCursor"],
    )


# Fetch every repository that should contribute to LOC stats, then hand the full list to the cache layer.
def loc_query(owner_affiliation, comment_size=0, force_cache=False):
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
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
        query_count("loc_query")
        variables = {
            "owner_affiliation": owner_affiliation,
            "login": USER_NAME,
            "cursor": cursor,
        }
        data = graphql_request("loc_query", query, variables)
        repositories = data["user"]["repositories"]
        edges.extend(repositories["edges"])

        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    return cache_builder(edges, comment_size, force_cache)


# Build the placeholder comment block stored at the top of each cache file.
def comment_block_lines(comment_size):
    return [CACHE_COMMENT_LINE for _ in range(comment_size)]


# Keep a cache file that stores one row per repository:
# repo hash, total commits, my commits, added LOC, deleted LOC.
# Rows are refreshed only when a repository's total commit count changes.
def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    cached = True
    filename = cache_file_path()

    try:
        with filename.open("r") as handle:
            data = handle.readlines()
    except FileNotFoundError:
        # When the cache does not exist yet, create it with the preserved comment block format.
        data = comment_block_lines(comment_size)
        with filename.open("w") as handle:
            handle.writelines(data)

    # If the repository set changed, rebuild the file skeleton so row order matches the current query.
    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with filename.open("r") as handle:
            data = handle.readlines()

    cache_header = data[:comment_size]
    cache_rows = data[comment_size:]

    for index, edge in enumerate(edges):
        repository_name = edge["node"]["nameWithOwner"]
        expected_hash = hashlib.sha256(repository_name.encode("utf-8")).hexdigest()
        stored_hash, stored_commit_count, *_ = cache_rows[index].split()

        # If the row no longer matches the current repository at this index, reset it from scratch.
        if stored_hash != expected_hash:
            cache_rows[index] = f"{expected_hash} 0 0 0 0\n"
            stored_hash = expected_hash
            stored_commit_count = "0"

        branch = edge["node"].get("defaultBranchRef")
        history = None if branch is None else branch["target"]["history"]
        current_commit_count = 0 if history is None else history["totalCount"]

        # Commit-count changes are the signal that this repository needs a fresh LOC recount.
        if int(stored_commit_count) != current_commit_count:
            cached = False
            if current_commit_count == 0:
                cache_rows[index] = f"{stored_hash} 0 0 0 0\n"
                continue

            owner, repo_name = repository_name.split("/", 1)
            additions, deletions, my_commits = recursive_loc(
                owner,
                repo_name,
                cache_rows,
                cache_header,
            )
            cache_rows[index] = (
                f"{stored_hash} {current_commit_count} {my_commits} "
                f"{additions} {deletions}\n"
            )

    # Persist the header and rows together so future runs see one consistent cache snapshot.
    with filename.open("w") as handle:
        handle.writelines(cache_header)
        handle.writelines(cache_rows)

    # Rebuild the aggregate totals from the final cache rows so the return value matches the file contents.
    for line in cache_rows:
        _, _, _, added_lines, deleted_lines = line.split()
        loc_add += int(added_lines)
        loc_del += int(deleted_lines)

    return [loc_add, loc_del, loc_add - loc_del, cached]


# Rewrite the cache file with one empty row per repository while preserving the top comment block.
def flush_cache(edges, filename, comment_size):
    try:
        with filename.open("r") as handle:
            cache_header = handle.readlines()[:comment_size]
    except FileNotFoundError:
        cache_header = []

    # Keep the cache header length stable even when the file is new or partially missing.
    if len(cache_header) < comment_size:
        cache_header.extend(comment_block_lines(comment_size - len(cache_header)))

    with filename.open("w") as handle:
        handle.writelines(cache_header[:comment_size])
        for edge in edges:
            repository_name = edge["node"]["nameWithOwner"]
            repository_hash = hashlib.sha256(repository_name.encode("utf-8")).hexdigest()
            handle.write(f"{repository_hash} 0 0 0 0\n")


# Merge historical stats from deleted repositories.
# If the archive file is absent, return zeros so CI and fresh clones still work.
def add_archive():
    if not ARCHIVE_PATH.exists():
        return [0, 0, 0, 0, 0]

    with ARCHIVE_PATH.open("r") as handle:
        lines = handle.readlines()

    added_loc = 0
    deleted_loc = 0
    saved_commits = 0
    contributed_repos = 0

    for line in lines:
        parts = line.split()

        # Archive rows are the only lines with a repo hash plus four numeric-ish columns.
        if len(parts) != 5 or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
            continue
        contributed_repos += 1
        added_loc += int(parts[3])
        deleted_loc += int(parts[4])
        if parts[2].isdigit():
            saved_commits += int(parts[2])

    # Some archive rows may be missing per-repo commit counts, so prefer the proof line if it exists.
    proof_match = re.search(r"total was (\d+)\.", "".join(lines))
    archived_commits = saved_commits
    if proof_match is not None:
        archived_commits = max(saved_commits, int(proof_match.group(1)))

    return [
        added_loc,
        deleted_loc,
        added_loc - deleted_loc,
        archived_commits,
        contributed_repos,
    ]


# Persist partially updated cache data before raising from a failed long-running LOC calculation.
def force_close_file(cache_rows, cache_header):
    filename = cache_file_path()
    with filename.open("w") as handle:
        handle.writelines(cache_header)
        handle.writelines(cache_rows)
    print(f"Saved partial cache data to {filename}.")


# Sum the stargazer counts for the repositories on one GraphQL page.
def stars_counter(edges):
    total_stars = 0
    for edge in edges:
        total_stars += edge["node"]["stargazers"]["totalCount"]
    return total_stars


# Open one SVG template, replace dynamic values, then align every rendered row.
def svg_overwrite(
    filename,
    age_data,
    commit_data,
    star_data,
    repo_data,
    contrib_data,
    follower_data,
    loc_data,
):
    tree = parse(filename)
    root = tree.getroot()

    # Replace all dynamic values before measuring text so spacing uses the final rendered content.
    replace_display_value(root, "age_data", age_data)
    replace_display_value(root, "commit_data", commit_data)
    replace_display_value(root, "star_data", star_data)
    replace_display_value(root, "repo_data", repo_data)
    replace_display_value(root, "contrib_data", contrib_data)
    replace_display_value(root, "follower_data", follower_data)
    replace_display_value(root, "loc_data", loc_data[2])
    replace_display_value(root, "loc_add", format_compact_number(loc_data[0]))
    replace_display_value(root, "loc_del", format_compact_number(loc_data[1]))

    align_simple_rows(root)
    align_stats_rows(root)
    align_loc_row(root)
    tree.write(filename, encoding="utf-8", xml_declaration=True)


# Normalize values to the exact text form shown inside the SVG card.
def format_display_text(value):
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


# Replace one required SVG value node and return the final visible text.
def replace_display_value(root, element_id, value):
    text = format_display_text(value)
    require_svg_element(root, element_id).text = text
    return text


# Return one required SVG node or fail clearly when the template structure is incomplete.
def require_svg_element(root, element_id):
    element = root.find(f".//*[@id='{element_id}']")
    if element is None:
        raise ValueError(f"missing required SVG element: {element_id}")
    return element


# Read the visible text of an SVG node, including text nested inside links.
def svg_visible_text(element):
    return "".join(element.itertext())


# Build a dot leader with an exact visible width.
def build_dot_leader(width):
    if width <= 0:
        return ""
    if width == 1:
        return " "
    if width == 2:
        return ". "
    return " " + ("." * (width - 2)) + " "


# Align one value row to a target width and keep one separator space on overflow.
def set_aligned_dots(
    root,
    dots_id,
    prefix_text,
    value_text,
    suffix_text="",
    target_width=PROFILE_ROW_WIDTH,
):
    requested_width = target_width - len(prefix_text) - len(value_text) - len(suffix_text)
    padding_width = max(1, requested_width)
    dots = build_dot_leader(padding_width)
    require_svg_element(root, dots_id).text = dots
    return len(prefix_text) + len(dots) + len(value_text) + len(suffix_text)


# Recompute every simple profile row from its current value in the SVG template.
def align_simple_rows(root):
    for dots_id, value_id, prefix_text in SIMPLE_ROW_SPECS:
        value_text = svg_visible_text(require_svg_element(root, value_id))
        set_aligned_dots(root, dots_id, prefix_text, value_text)


# Keep the second GitHub Stats column at its configured starting position when possible.
def stats_separator(current_width):
    return (" " * max(0, STATS_LEFT_COLUMN_WIDTH - current_width)) + STATS_SEPARATOR


# Align both two-column GitHub Stats rows from the final displayed values.
def align_stats_rows(root):
    repo_text = svg_visible_text(require_svg_element(root, "repo_data"))
    contrib_text = svg_visible_text(require_svg_element(root, "contrib_data"))
    star_text = svg_visible_text(require_svg_element(root, "star_data"))
    commit_text = svg_visible_text(require_svg_element(root, "commit_data"))
    follower_text = svg_visible_text(require_svg_element(root, "follower_data"))

    repo_suffix = f" {{Contributed: {contrib_text}}}"
    repo_left_width = set_aligned_dots(
        root,
        "repo_data_dots",
        ". Repos:",
        repo_text,
        suffix_text=repo_suffix,
        target_width=STATS_LEFT_COLUMN_WIDTH,
    )
    repo_gap = stats_separator(repo_left_width)
    require_svg_element(root, "repo_stats_gap").text = repo_gap
    repo_dots = require_svg_element(root, "repo_data_dots").text or ""
    set_aligned_dots(
        root,
        "star_data_dots",
        f". Repos:{repo_dots}{repo_text}{repo_suffix}{repo_gap}Stars:",
        star_text,
        target_width=PROFILE_ROW_WIDTH,
    )

    commit_left_width = set_aligned_dots(
        root,
        "commit_data_dots",
        ". Commits:",
        commit_text,
        target_width=STATS_LEFT_COLUMN_WIDTH,
    )
    commit_gap = stats_separator(commit_left_width)
    require_svg_element(root, "commit_stats_gap").text = commit_gap
    commit_dots = require_svg_element(root, "commit_data_dots").text or ""
    set_aligned_dots(
        root,
        "follower_data_dots",
        f". Commits:{commit_dots}{commit_text}{commit_gap}Followers:",
        follower_text,
        target_width=PROFILE_ROW_WIDTH,
    )


# Align the complete LOC row while keeping the deletion fragment free of dot padding.
def align_loc_row(root):
    net_text = svg_visible_text(require_svg_element(root, "loc_data"))
    added_text = svg_visible_text(require_svg_element(root, "loc_add"))
    deleted_text = svg_visible_text(require_svg_element(root, "loc_del"))
    suffix = f" ( +{added_text}, -{deleted_text} )"
    set_aligned_dots(
        root,
        "loc_data_dots",
        ". GitHub LOC:",
        net_text,
        suffix_text=suffix,
        target_width=PROFILE_ROW_WIDTH,
    )
    require_svg_element(root, "loc_del_dots").text = ""


# Shorten large numeric values so the SVG does not overflow when LOC totals become very large.
def format_compact_number(value):
    if isinstance(value, str):
        normalized = value.replace(",", "").strip().upper()

        # Already-compact values can pass straight through on rerenders.
        if normalized.endswith("M"):
            return value
        if normalized.endswith("K"):
            return value
        value = int(normalized)

    absolute_value = abs(value)
    if absolute_value >= 1_000_000:
        formatted = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}M"
    if absolute_value >= 1_000:
        formatted = f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{formatted}K"
    return str(value)


# Read the cache file and sum only the "my commits" column for the final README stat.
def commit_counter(comment_size):
    total_commits = 0
    filename = cache_file_path()
    with filename.open("r") as handle:
        data = handle.readlines()
    for line in data[comment_size:]:
        total_commits += int(line.split()[2])
    return total_commits


# Fetch the GitHub user id used later to identify which commits belong to the current profile.
def user_getter(username):
    query_count("user_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            id
        }
    }"""
    data = graphql_request("user_getter", query, {"login": username})
    return data["user"]["id"]


# Fetch the follower count shown on the SVG card.
def follower_getter(username):
    query_count("follower_getter")
    query = """
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }"""
    data = graphql_request("follower_getter", query, {"login": username})
    return int(data["user"]["followers"]["totalCount"])


# Increment the per-function GraphQL counters reported at the end of the script.
def query_count(function_name):
    QUERY_COUNT[function_name] += 1


# Run one function and return both its result and the elapsed wall-clock time.
def perf_counter(function, *args):
    start = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter() - start


# Print one timing line in a compact human-readable format.
def print_duration(label, duration):
    metric = f"{duration:.4f} s" if duration > 1 else f"{duration * 1000:.4f} ms"
    print(f"   {label + ':':<20}{metric:>12}")


# Apply the same computed values to both SVG variants used by the README.
def update_svg_files(
    age_data,
    commit_data,
    star_data,
    repo_data,
    contrib_data,
    follower_data,
    loc_data,
):
    for svg_file in SVG_FILES:
        svg_overwrite(
            svg_file,
            age_data,
            commit_data,
            star_data,
            repo_data,
            contrib_data,
            follower_data,
            loc_data,
        )


# Main pipeline:
# 1. load credentials
# 2. fetch GitHub stats
# 3. refresh or reuse cache data
# 4. merge archived repository stats when applicable
# 5. write both SVG files
# 6. print timing and query diagnostics
def main():
    global OWNER_ID

    configure_environment()

    print("Calculation times:")

    OWNER_ID, user_time = perf_counter(user_getter, USER_NAME)
    print(OWNER_ID)
    print_duration("account data", user_time)

    age_data, age_time = perf_counter(format_age, BIRTHDAY)
    print_duration("age calculation", age_time)

    total_loc, loc_time = perf_counter(
        loc_query,
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
        COMMENT_BLOCK_SIZE,
    )
    print_duration("LOC (cached)" if total_loc[-1] else "LOC (no cache)", loc_time)

    commit_data, commit_time = perf_counter(commit_counter, COMMENT_BLOCK_SIZE)
    print_duration("commit count", commit_time)

    star_data, star_time = perf_counter(graph_repos_stars, "stars", ["OWNER"])
    print_duration("stars", star_time)

    repo_data, repo_time = perf_counter(graph_repos_stars, "repos", ["OWNER"])
    print_duration("repos", repo_time)

    contrib_data, contrib_time = perf_counter(
        graph_repos_stars,
        "repos",
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
    )
    print_duration("contributed repos", contrib_time)

    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)
    print_duration("followers", follower_time)

    # Only this specific user has deleted-repository stats tracked in the archive file.
    if OWNER_ID == ARCHIVE_USER_ID:
        archived_data = add_archive()
        for index in range(len(total_loc) - 1):
            total_loc[index] += archived_data[index]
        contrib_data += archived_data[-1]
        commit_data += archived_data[-2]

    # Keep the boolean cache flag in the last slot untouched and format only the displayed LOC values.
    total_loc[:-1] = [f"{value:,}" for value in total_loc[:-1]]

    update_svg_files(
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        total_loc[:-1],
    )

    total_runtime = (
        user_time
        + age_time
        + loc_time
        + commit_time
        + star_time
        + repo_time
        + contrib_time
        + follower_time
    )
    print(f"{'Total function time:':<21} {total_runtime:>11.4f} s")
    print(f"Total GitHub GraphQL API calls: {sum(QUERY_COUNT.values()):>3}")
    for function_name, count in QUERY_COUNT.items():
        print(f"   {function_name + ':':<25} {count:>6}")


# Run the README generator only when this file is executed directly.
if __name__ == "__main__":
    main()
