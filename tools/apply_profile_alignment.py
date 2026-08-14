from pathlib import Path

from lxml.etree import parse

TODAY_PATH = Path("today.py")
SVG_PATHS = (Path("dark_mode.svg"), Path("light_mode.svg"))
SVG_NS = "http://www.w3.org/2000/svg"

OLD_CONSTANTS = '''# Visual widths used when inserting dot padding in the SVG text fields.
AGE_DATA_WIDTH = 49
COMMIT_DATA_WIDTH = 22
LOC_DATA_WIDTH = 25
FOLLOWER_DATA_WIDTH = 10
REPO_DATA_WIDTH = 6
STAR_DATA_WIDTH = 14
STATS_SECONDARY_COLUMN_WIDTH = 34
STATS_SECONDARY_SEPARATOR = " |  "
'''

NEW_CONSTANTS = '''# Shared visible widths used by the profile card alignment engine.
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
'''

START_MARKER = "# Open one SVG template and replace the dynamic text fields used by the README card.\n"
END_MARKER = "# Shorten large numeric values so the SVG does not overflow when LOC totals become very large.\n"

NEW_RENDERER = '''# Open one SVG template, replace dynamic values, then align every rendered row.
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


'''

SIMPLE_ROWS = {
    "50": ("os_dots", "os_value"),
    "70": ("age_data_dots", "age_data"),
    "90": ("host_dots", "host_value"),
    "110": ("kernel_dots", "kernel_value"),
    "130": ("ide_dots", "ide_value"),
    "170": ("languages_application_dots", "languages_application_value"),
    "190": ("languages_systems_dots", "languages_systems_value"),
    "210": ("languages_spoken_dots", "languages_spoken_value"),
    "250": ("hobbies_software_dots", "hobbies_software_value"),
    "270": ("hobbies_hardware_dots", "hobbies_hardware_value"),
    "290": ("hobbies_science_dots", "hobbies_science_value"),
    "350": ("portfolio_dots", "portfolio_value"),
    "370": ("email_dots", "email_value"),
    "390": ("instagram_dots", "instagram_value"),
    "410": ("discord_dots", "discord_value"),
}

SEPARATORS = {
    "30": 42,
    "320": 50,
    "450": 45,
}


def patch_today():
    source = TODAY_PATH.read_text(encoding="utf-8")
    if source.count(OLD_CONSTANTS) != 1:
        raise RuntimeError("today.py constants block did not match expected baseline")
    source = source.replace(OLD_CONSTANTS, NEW_CONSTANTS)
    if source.count(START_MARKER) != 1 or source.count(END_MARKER) != 1:
        raise RuntimeError("today.py renderer markers did not match expected baseline")
    start = source.index(START_MARKER)
    end = source.index(END_MARKER)
    source = source[:start] + NEW_RENDERER + source[end:]
    TODAY_PATH.write_text(source, encoding="utf-8")


def row_nodes(main_text, y):
    children = list(main_text)
    for index, node in enumerate(children):
        if node.get("y") == y:
            row = [node]
            for following in children[index + 1 :]:
                if following.get("y") is not None:
                    break
                row.append(following)
            return row
    raise RuntimeError(f"missing SVG row y={y}")


def patch_svg(path):
    tree = parse(path)
    root = tree.getroot()
    texts = root.findall(f"{{{SVG_NS}}}text")
    if len(texts) < 2:
        raise RuntimeError(f"missing profile text block in {path}")
    main_text = texts[1]

    for y, (dots_id, value_id) in SIMPLE_ROWS.items():
        row = row_nodes(main_text, y)
        dot_nodes = [node for node in row if node.get("class") == "cc"]
        value_nodes = [node for node in row if node.get("class") == "value"]
        if len(dot_nodes) < 2 or len(value_nodes) != 1:
            raise RuntimeError(f"unexpected aligned row structure in {path} at y={y}")
        dot_nodes[-1].set("id", dots_id)
        value_nodes[0].set("id", value_id)

    for y, hyphen_count in SEPARATORS.items():
        row = row_nodes(main_text, y)
        row[0].tail = " " + ("-" * hyphen_count) + "\n"

    tree.write(path, encoding="utf-8", xml_declaration=True)


def align_templates():
    namespace = {}
    exec(TODAY_PATH.read_text(encoding="utf-8"), namespace)
    for path in SVG_PATHS:
        tree = parse(path)
        root = tree.getroot()
        namespace["align_simple_rows"](root)
        namespace["align_stats_rows"](root)
        namespace["align_loc_row"](root)
        tree.write(path, encoding="utf-8", xml_declaration=True)


def main():
    patch_today()
    for path in SVG_PATHS:
        patch_svg(path)
    align_templates()

    targets = (TODAY_PATH, *SVG_PATHS)
    for path in targets:
        if chr(0x2014) in path.read_text(encoding="utf-8"):
            raise RuntimeError(f"U+2014 remains in {path}")


if __name__ == "__main__":
    main()
