# Profile Card Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual SVG dot counts and LOC-specific spacing patches with one reusable alignment engine that keeps every profile row aligned automatically as values change.

**Architecture:** Keep `dark_mode.svg` and `light_mode.svg` as visual templates, add stable ids to every aligned dot leader and value node, and centralize all spacing calculations in `today.py`. Use one 60-character target width for normal profile rows, preserve a 34-character left column target for the two-column GitHub Stats rows, and remove the alignment monkey patches from `generate_readme.py` once the core renderer owns all spacing.

**Tech Stack:** Python 3.12, standard-library `unittest`, `lxml`, SVG/XML, GitHub Actions.

## Global Constraints

- Preserve the current card design, colors, font, field content, GitHub statistics semantics, and LOC calculation.
- Do not move the full SVG generation into Python.
- Both SVG themes must use the same alignment ids and the same alignment behavior.
- Simple profile rows use a shared target width of exactly 60 visible monospace characters when their values fit.
- The left side of each two-column GitHub Stats row targets exactly 34 visible characters before the ` |  ` separator.
- If a value exceeds a target width, keep at least one separating space and allow the row to extend to the right.
- The LOC deletion fragment must remain `, -VALUE` with no dot leader between the comma and minus sign.
- The final LOC parenthesis targets the same 60-character right edge when the row fits.
- No U+2014 character may remain in any file modified by this work, including comments, docstrings, Markdown, tests, workflow YAML, Python, and SVG content.
- Use ASCII hyphen `-` for the three decorative section separators in both SVG files.
- Tests must not use the network.
- Do not add a new testing dependency. Use `unittest`, because the current requirements contain only `python-dateutil`, `requests`, `lxml`, and `python-dotenv`.

---

## File Structure

**Create:**
- `tests/test_alignment.py`: pure formatting tests, template structure tests, local SVG rendering tests, overflow tests, and U+2014 checks.

**Modify:**
- `today.py`: generic alignment primitives, template configuration, dynamic value replacement, GitHub Stats layout, LOC layout, and final SVG rendering.
- `generate_readme.py`: keep only GitHub Actions-safe data acquisition overrides and delegate all rendering to `today.py`.
- `dark_mode.svg`: stable alignment ids and ASCII separators.
- `light_mode.svg`: the exact same stable alignment ids and ASCII separators.
- `.github/workflows/build.yaml`: run the local test suite after dependency installation and before regenerating the README SVG files.

**Do not modify:**
- `README.md`, unless a later verification proves the existing references to the two SVG files are broken. The current references are already correct.
- `cache/requirements.txt`, because `unittest` is in the Python standard library and `lxml` is already installed.

---

### Task 1: Build the generic alignment primitives with TDD

**Files:**
- Create: `tests/test_alignment.py`
- Modify: `today.py:20-45, 520-620`

**Interfaces:**
- Produces: `PROFILE_ROW_WIDTH: int = 60`
- Produces: `STATS_LEFT_COLUMN_WIDTH: int = 34`
- Produces: `STATS_SEPARATOR: str = " |  "`
- Produces: `require_svg_element(root, element_id)`
- Produces: `svg_visible_text(element) -> str`
- Produces: `build_dot_leader(width: int) -> str`
- Produces: `set_aligned_dots(root, dots_id: str, prefix_text: str, value_text: str, suffix_text: str = "", target_width: int = PROFILE_ROW_WIDTH) -> int`
- Consumes: existing `format_display_text()` and `find_and_replace()` behavior only until later tasks replace silent lookups in alignment paths.

- [ ] **Step 1: Create the first failing unit tests for dot leader widths**

Create `tests/test_alignment.py` with:

```python
import unittest
from lxml.etree import fromstring

import today


class DotLeaderTests(unittest.TestCase):
    def test_dot_leader_widths(self):
        self.assertEqual(today.build_dot_leader(0), "")
        self.assertEqual(today.build_dot_leader(1), " ")
        self.assertEqual(today.build_dot_leader(2), ". ")
        self.assertEqual(today.build_dot_leader(6), " .... ")

    def test_missing_required_id_raises(self):
        root = fromstring("<svg><tspan id='other'>x</tspan></svg>")
        with self.assertRaisesRegex(ValueError, "missing required SVG element: dots"):
            today.require_svg_element(root, "dots")

    def test_visible_text_includes_nested_anchor_text(self):
        root = fromstring(
            "<svg><tspan id='value'>before<a>vikbg.github.io/portfolio</a>after</tspan></svg>"
        )
        value = today.require_svg_element(root, "value")
        self.assertEqual(
            today.svg_visible_text(value),
            "beforevikbg.github.io/portfolioafter",
        )
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing functions**

Run:

```bash
python -m unittest tests.test_alignment.DotLeaderTests -v
```

Expected: FAIL because `build_dot_leader`, `require_svg_element`, and `svg_visible_text` do not exist yet.

- [ ] **Step 3: Add the shared layout constants and minimal helpers to `today.py`**

Replace the old per-field width constants with meaningful layout constants:

```python
PROFILE_ROW_WIDTH = 60
STATS_LEFT_COLUMN_WIDTH = 34
STATS_SEPARATOR = " |  "
```

Add:

```python
def require_svg_element(root, element_id):
    element = root.find(f".//*[@id='{element_id}']")
    if element is None:
        raise ValueError(f"missing required SVG element: {element_id}")
    return element


def svg_visible_text(element):
    return "".join(element.itertext())


def build_dot_leader(width):
    if width <= 0:
        return ""
    if width == 1:
        return " "
    if width == 2:
        return ". "
    return " " + ("." * (width - 2)) + " "
```

- [ ] **Step 4: Add failing tests for generic row alignment and overflow**

Append:

```python
class GenericAlignmentTests(unittest.TestCase):
    def make_root(self):
        return fromstring("<svg><tspan id='dots'></tspan></svg>")

    def test_short_value_gets_more_padding(self):
        root = self.make_root()
        width = today.set_aligned_dots(root, "dots", ". Example:", "x", target_width=20)
        dots = today.require_svg_element(root, "dots").text
        self.assertEqual(width, 20)
        self.assertEqual(len(dots), 9)

    def test_longer_value_gets_less_padding(self):
        short_root = self.make_root()
        long_root = self.make_root()
        today.set_aligned_dots(short_root, "dots", ". Example:", "x", target_width=30)
        today.set_aligned_dots(long_root, "dots", ". Example:", "abcdefghij", target_width=30)
        short_dots = today.require_svg_element(short_root, "dots").text
        long_dots = today.require_svg_element(long_root, "dots").text
        self.assertGreater(len(short_dots), len(long_dots))

    def test_overflow_keeps_one_separator_space(self):
        root = self.make_root()
        width = today.set_aligned_dots(
            root,
            "dots",
            ". VeryLongLabel:",
            "value-that-is-longer-than-the-target",
            target_width=20,
        )
        dots = today.require_svg_element(root, "dots").text
        self.assertEqual(dots, " ")
        self.assertGreater(width, 20)
```

- [ ] **Step 5: Run the new tests and verify they fail because `set_aligned_dots` is missing**

Run:

```bash
python -m unittest tests.test_alignment.GenericAlignmentTests -v
```

Expected: FAIL with `AttributeError` for `set_aligned_dots`.

- [ ] **Step 6: Implement `set_aligned_dots` using only the shared dot helper**

Add:

```python
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
```

- [ ] **Step 7: Run all Task 1 tests**

Run:

```bash
python -m unittest tests.test_alignment.DotLeaderTests tests.test_alignment.GenericAlignmentTests -v
```

Expected: PASS.

- [ ] **Step 8: Self-review checkpoint 1, core algorithm**

Check all of the following before moving on:

```text
[ ] Only build_dot_leader constructs repeated dot strings.
[ ] PROFILE_ROW_WIDTH is defined once and equals 60.
[ ] STATS_LEFT_COLUMN_WIDTH is defined once and equals 34.
[ ] Overflow clamps to one separating space.
[ ] Missing required ids raise ValueError and do not fail silently.
[ ] No U+2014 exists in tests/test_alignment.py or the modified today.py section.
```

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in (Path("today.py"), Path("tests/test_alignment.py")):
    assert "\u2014" not in path.read_text(encoding="utf-8"), path
print("U+2014 check passed")
PY
```

Expected: `U+2014 check passed`.

- [ ] **Step 9: Commit Task 1**

```bash
git add today.py tests/test_alignment.py
git commit -m "test: add generic profile alignment primitives"
```

---

### Task 2: Migrate both SVG templates to explicit alignment ids and ASCII separators

**Files:**
- Modify: `dark_mode.svg:46-70`
- Modify: `light_mode.svg:46-70`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Consumes: `require_svg_element()` from Task 1.
- Produces: identical stable ids in both SVG templates.
- Produces: `SIMPLE_ROW_SPECS` compatible value ids for Task 3.

Required simple-row id pairs:

```text
os_dots / os_value
age_data_dots / age_data
host_dots / host_value
kernel_dots / kernel_value
ide_dots / ide_value
languages_application_dots / languages_application_value
languages_systems_dots / languages_systems_value
languages_spoken_dots / languages_spoken_value
hobbies_software_dots / hobbies_software_value
hobbies_hardware_dots / hobbies_hardware_value
hobbies_science_dots / hobbies_science_value
portfolio_dots / portfolio_value
email_dots / email_value
instagram_dots / instagram_value
discord_dots / discord_value
```

The existing GitHub Stats ids remain:

```text
repo_data_dots
repo_data
contrib_data
repo_stats_gap
star_data_dots
star_data
commit_data_dots
commit_data
commit_stats_gap
follower_data_dots
follower_data
loc_data_dots
loc_data
loc_add
loc_del_dots
loc_del
```

- [ ] **Step 1: Add failing template parity and prohibited-character tests**

Append:

```python
from pathlib import Path
from lxml.etree import parse


TEMPLATE_PATHS = (Path("dark_mode.svg"), Path("light_mode.svg"))
SIMPLE_IDS = {
    "os_dots", "os_value", "age_data_dots", "age_data",
    "host_dots", "host_value", "kernel_dots", "kernel_value",
    "ide_dots", "ide_value",
    "languages_application_dots", "languages_application_value",
    "languages_systems_dots", "languages_systems_value",
    "languages_spoken_dots", "languages_spoken_value",
    "hobbies_software_dots", "hobbies_software_value",
    "hobbies_hardware_dots", "hobbies_hardware_value",
    "hobbies_science_dots", "hobbies_science_value",
    "portfolio_dots", "portfolio_value", "email_dots", "email_value",
    "instagram_dots", "instagram_value", "discord_dots", "discord_value",
}


class TemplateStructureTests(unittest.TestCase):
    def ids_for(self, path):
        root = parse(path).getroot()
        return {element.get("id") for element in root.iter() if element.get("id")}

    def test_themes_expose_all_simple_alignment_ids(self):
        for path in TEMPLATE_PATHS:
            with self.subTest(path=path):
                self.assertTrue(SIMPLE_IDS.issubset(self.ids_for(path)))

    def test_themes_have_matching_alignment_ids(self):
        dark_ids = self.ids_for(TEMPLATE_PATHS[0])
        light_ids = self.ids_for(TEMPLATE_PATHS[1])
        self.assertEqual(dark_ids, light_ids)

    def test_modified_target_files_have_no_u2014(self):
        paths = (
            Path("today.py"),
            Path("generate_readme.py"),
            Path("dark_mode.svg"),
            Path("light_mode.svg"),
            Path("tests/test_alignment.py"),
            Path(".github/workflows/build.yaml"),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn("\u2014", path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run template tests and verify they fail**

Run:

```bash
python -m unittest tests.test_alignment.TemplateStructureTests -v
```

Expected: FAIL because the simple SVG nodes do not yet have the required ids and the current SVG separators contain U+2014.

- [ ] **Step 3: Add ids to every simple aligned dot node and value node in both SVG files**

Use the exact ids listed above. Keep the current visible text unchanged.

For the portfolio row, put `id="portfolio_value"` on the outer value `tspan`, not on the nested `a`, so `svg_visible_text()` can read the nested link text through `itertext()`.

Example transformation:

```xml
<tspan class="cc" id="languages_application_dots"> ............ </tspan><tspan class="value" id="languages_application_value">Python, TypeScript, C#</tspan>
```

Apply the same id structure to both themes.

- [ ] **Step 4: Replace all decorative U+2014 separator characters in both SVG files with ASCII hyphens**

Keep each separator at 60 visible characters total:

```text
viktor@serhiienko ------------------------------------------
- Contact --------------------------------------------------
- GitHub Stats ---------------------------------------------
```

The exact hyphen counts are 42 after the profile name, 50 after `- Contact`, and 45 after `- GitHub Stats`.

- [ ] **Step 5: Run template tests again**

Run:

```bash
python -m unittest tests.test_alignment.TemplateStructureTests -v
```

Expected: PASS.

- [ ] **Step 6: Self-review checkpoint 2, template migration**

Verify:

```text
[ ] Every required simple dot id exists once in dark_mode.svg.
[ ] Every required simple value id exists once in dark_mode.svg.
[ ] The exact same ids exist once in light_mode.svg.
[ ] No profile value text changed.
[ ] Portfolio still contains the same href and visible link.
[ ] Colors, coordinates, font settings, and ASCII art are unchanged.
[ ] All three decorative separators contain only ASCII hyphens.
[ ] No U+2014 exists in either SVG.
```

- [ ] **Step 7: Commit Task 2**

```bash
git add dark_mode.svg light_mode.svg tests/test_alignment.py
git commit -m "refactor: identify profile card alignment fields"
```

---

### Task 3: Align every simple profile row from one configuration table

**Files:**
- Modify: `today.py:25-55, 540-650`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Consumes: `PROFILE_ROW_WIDTH`, `require_svg_element`, `svg_visible_text`, `set_aligned_dots`.
- Produces: `SIMPLE_ROW_SPECS: tuple[tuple[str, str, str], ...]`
- Produces: `align_simple_rows(root) -> None`
- Produces: `replace_display_value(root, element_id: str, value) -> str`

- [ ] **Step 1: Add failing tests for simple row alignment using a real template copy in memory**

Append:

```python
class SimpleRowAlignmentTests(unittest.TestCase):
    def parse_dark(self):
        return parse("dark_mode.svg").getroot()

    def row_width(self, root, dots_id, value_id, prefix):
        dots = today.require_svg_element(root, dots_id).text or ""
        value = today.svg_visible_text(today.require_svg_element(root, value_id))
        return len(prefix) + len(dots) + len(value)

    def test_current_simple_rows_align_to_profile_width(self):
        root = self.parse_dark()
        today.align_simple_rows(root)
        for dots_id, value_id, prefix in today.SIMPLE_ROW_SPECS:
            with self.subTest(dots_id=dots_id):
                self.assertEqual(
                    self.row_width(root, dots_id, value_id, prefix),
                    today.PROFILE_ROW_WIDTH,
                )

    def test_longer_language_value_reduces_dot_count(self):
        root = self.parse_dark()
        value = today.require_svg_element(root, "languages_application_value")
        original = today.require_svg_element(root, "languages_application_dots").text or ""
        value.text = "Python, TypeScript, C#, JavaScript"
        today.align_simple_rows(root)
        updated = today.require_svg_element(root, "languages_application_dots").text or ""
        self.assertLess(len(updated), len(original))

    def test_long_contact_value_overflows_readably(self):
        root = self.parse_dark()
        value = today.require_svg_element(root, "email_value")
        value.text = "a-very-long-email-address-that-exceeds-the-normal-row-width@example.com"
        today.align_simple_rows(root)
        dots = today.require_svg_element(root, "email_dots").text
        self.assertEqual(dots, " ")
```

- [ ] **Step 2: Run the tests and verify they fail because configuration and alignment are missing**

Run:

```bash
python -m unittest tests.test_alignment.SimpleRowAlignmentTests -v
```

Expected: FAIL for missing `SIMPLE_ROW_SPECS` and `align_simple_rows`.

- [ ] **Step 3: Add one explicit configuration table in `today.py`**

Use exactly:

```python
SIMPLE_ROW_SPECS = (
    ("os_dots", "os_value", ". OS:"),
    ("age_data_dots", "age_data", ". Uptime:"),
    ("host_dots", "host_value", ". Host:"),
    ("kernel_dots", "kernel_value", ". Kernel:"),
    ("ide_dots", "ide_value", ". IDE:"),
    ("languages_application_dots", "languages_application_value", ". Languages.Application:"),
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
```

- [ ] **Step 4: Implement display replacement and the simple alignment pass**

Add:

```python
def replace_display_value(root, element_id, value):
    text = format_display_text(value)
    require_svg_element(root, element_id).text = text
    return text


def align_simple_rows(root):
    for dots_id, value_id, prefix_text in SIMPLE_ROW_SPECS:
        value_text = svg_visible_text(require_svg_element(root, value_id))
        set_aligned_dots(
            root,
            dots_id,
            prefix_text,
            value_text,
            target_width=PROFILE_ROW_WIDTH,
        )
```

- [ ] **Step 5: Run all simple-row tests**

Run:

```bash
python -m unittest tests.test_alignment.SimpleRowAlignmentTests -v
```

Expected: PASS.

- [ ] **Step 6: Verify all current simple rows calculate to exactly 60 characters in both themes**

Add and run this temporary verification command without committing a separate script:

```bash
python - <<'PY'
from lxml.etree import parse
import today

for filename in today.SVG_FILES:
    root = parse(filename).getroot()
    today.align_simple_rows(root)
    for dots_id, value_id, prefix in today.SIMPLE_ROW_SPECS:
        dots = today.require_svg_element(root, dots_id).text or ""
        value = today.svg_visible_text(today.require_svg_element(root, value_id))
        width = len(prefix) + len(dots) + len(value)
        assert width == today.PROFILE_ROW_WIDTH, (filename, dots_id, width)
print("simple rows aligned")
PY
```

Expected: `simple rows aligned`.

- [ ] **Step 7: Commit Task 3**

```bash
git add today.py tests/test_alignment.py
git commit -m "feat: align all simple profile rows dynamically"
```

---

### Task 4: Move GitHub Stats and LOC onto the same alignment engine

**Files:**
- Modify: `today.py:520-640`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Consumes: `set_aligned_dots`, `replace_display_value`, `PROFILE_ROW_WIDTH`, `STATS_LEFT_COLUMN_WIDTH`, `STATS_SEPARATOR`.
- Produces: `stats_separator(current_width: int) -> str`
- Produces: `align_stats_rows(root) -> None`
- Produces: `align_loc_row(root) -> None`
- Removes: `justify_format()`
- Removes: `build_dot_string()`
- Removes: `secondary_stat_gap()`
- Removes: `repo_stats_left_width()`
- Removes: `commit_stats_left_width()`
- Removes: old per-field width constants `AGE_DATA_WIDTH`, `COMMIT_DATA_WIDTH`, `LOC_DATA_WIDTH`, `FOLLOWER_DATA_WIDTH`, `REPO_DATA_WIDTH`, and `STAR_DATA_WIDTH`.

- [ ] **Step 1: Add failing two-column stats tests**

Append:

```python
class StatsAlignmentTests(unittest.TestCase):
    def parse_dark(self):
        return parse("dark_mode.svg").getroot()

    def set_value(self, root, element_id, value):
        today.require_svg_element(root, element_id).text = today.format_display_text(value)

    def visible_stats_row_width(self, root, row):
        if row == "repos":
            repo = today.svg_visible_text(today.require_svg_element(root, "repo_data"))
            contrib = today.svg_visible_text(today.require_svg_element(root, "contrib_data"))
            stars = today.svg_visible_text(today.require_svg_element(root, "star_data"))
            return len(
                ". Repos:"
                + (today.require_svg_element(root, "repo_data_dots").text or "")
                + repo
                + f" {{Contributed: {contrib}}}"
                + (today.require_svg_element(root, "repo_stats_gap").text or "")
                + "Stars:"
                + (today.require_svg_element(root, "star_data_dots").text or "")
                + stars
            )
        commits = today.svg_visible_text(today.require_svg_element(root, "commit_data"))
        followers = today.svg_visible_text(today.require_svg_element(root, "follower_data"))
        return len(
            ". Commits:"
            + (today.require_svg_element(root, "commit_data_dots").text or "")
            + commits
            + (today.require_svg_element(root, "commit_stats_gap").text or "")
            + "Followers:"
            + (today.require_svg_element(root, "follower_data_dots").text or "")
            + followers
        )

    def test_stats_rows_align_for_normal_values(self):
        root = self.parse_dark()
        today.align_stats_rows(root)
        self.assertEqual(self.visible_stats_row_width(root, "repos"), 60)
        self.assertEqual(self.visible_stats_row_width(root, "commits"), 60)

    def test_commit_and_follower_widths_adapt(self):
        for commits, followers in ((9, 9), (99, 99), (999, 999), (1000, 1000), (100000, 100000)):
            with self.subTest(commits=commits, followers=followers):
                root = self.parse_dark()
                self.set_value(root, "commit_data", commits)
                self.set_value(root, "follower_data", followers)
                today.align_stats_rows(root)
                width = self.visible_stats_row_width(root, "commits")
                if width <= today.PROFILE_ROW_WIDTH:
                    self.assertEqual(width, today.PROFILE_ROW_WIDTH)
                else:
                    self.assertGreater(width, today.PROFILE_ROW_WIDTH)
```

- [ ] **Step 2: Add failing LOC alignment tests**

Append to the same class:

```python
    def loc_width(self, root):
        net = today.svg_visible_text(today.require_svg_element(root, "loc_data"))
        added = today.svg_visible_text(today.require_svg_element(root, "loc_add"))
        deleted = today.svg_visible_text(today.require_svg_element(root, "loc_del"))
        dots = today.require_svg_element(root, "loc_data_dots").text or ""
        return len(f". GitHub LOC:{dots}{net} ( +{added}, -{deleted} )")

    def test_loc_row_targets_profile_width(self):
        root = self.parse_dark()
        today.align_loc_row(root)
        self.assertEqual(self.loc_width(root), today.PROFILE_ROW_WIDTH)
        self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")

    def test_loc_row_adapts_to_compact_value_lengths(self):
        root = self.parse_dark()
        self.set_value(root, "loc_data", "1,234,567")
        self.set_value(root, "loc_add", "1.3M")
        self.set_value(root, "loc_del", "765.4K")
        today.align_loc_row(root)
        self.assertEqual(self.loc_width(root), today.PROFILE_ROW_WIDTH)
        self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")
```

- [ ] **Step 3: Run stats tests and verify they fail for missing new functions**

Run:

```bash
python -m unittest tests.test_alignment.StatsAlignmentTests -v
```

Expected: FAIL for missing `align_stats_rows` and `align_loc_row`.

- [ ] **Step 4: Implement the stats separator helper**

Add:

```python
def stats_separator(current_width):
    return (" " * max(0, STATS_LEFT_COLUMN_WIDTH - current_width)) + STATS_SEPARATOR
```

- [ ] **Step 5: Implement `align_stats_rows` using the generic dot helper**

Use this structure:

```python
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
    set_aligned_dots(
        root,
        "star_data_dots",
        ". Repos:" + (require_svg_element(root, "repo_data_dots").text or "") + repo_text + repo_suffix + repo_gap + "Stars:",
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
    set_aligned_dots(
        root,
        "follower_data_dots",
        ". Commits:" + (require_svg_element(root, "commit_data_dots").text or "") + commit_text + commit_gap + "Followers:",
        follower_text,
        target_width=PROFILE_ROW_WIDTH,
    )
```

The long prefix passed for the right column is deliberate. It makes the generic helper calculate the final full-row width rather than relying on a second set of field-specific constants.

- [ ] **Step 6: Implement `align_loc_row` using the same generic helper**

Add:

```python
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
```

- [ ] **Step 7: Refactor `svg_overwrite` to replace values first, then align once**

The body becomes conceptually:

```python
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
```

- [ ] **Step 8: Remove obsolete alignment helpers and constants**

Delete only the no-longer-used alignment code listed in this task's Interfaces block. Keep unrelated cache, API, LOC counting, and formatting logic unchanged.

- [ ] **Step 9: Run all tests**

Run:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 10: Self-review checkpoint 3, stats and LOC**

Verify:

```text
[ ] Repos and Commits left segments target 34 characters.
[ ] Stars and Followers use the full rendered prefix to target 60 characters.
[ ] LOC uses the same set_aligned_dots helper as normal rows.
[ ] loc_del_dots is always empty after rendering.
[ ] No old per-field dot-width constant remains.
[ ] No duplicate dot-builder exists in today.py.
[ ] Current rows render to 60 characters in both themes.
[ ] Overflow values remain readable instead of creating negative padding.
```

- [ ] **Step 11: Commit Task 4**

```bash
git add today.py tests/test_alignment.py
git commit -m "refactor: unify GitHub stats alignment"
```

---

### Task 5: Remove the GitHub Actions rendering monkey patches and run tests in CI

**Files:**
- Modify: `generate_readme.py:1-170`
- Modify: `.github/workflows/build.yaml:15-32`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Consumes: final `today.py` rendering API from Tasks 1 through 4.
- Keeps: `public_repository_stats`, `repository_connection_count`, `actions_safe_repo_stats`.
- Removes from `generate_readme.py`: `lxml.etree.parse` import, `_ORIGINAL_JUSTIFY_FORMAT`, `_ORIGINAL_SVG_OVERWRITE`, `readme_justify_format`, `stats_row_width`, `loc_dot_padding`, and `readme_svg_overwrite`.
- Final `main()` only patches `today.graph_repos_stars` before calling `today.main()`.

- [ ] **Step 1: Add a regression test that the wrapper no longer exports alignment patches**

Append:

```python
class WrapperSeparationTests(unittest.TestCase):
    def test_generate_readme_does_not_define_alignment_wrappers(self):
        source = Path("generate_readme.py").read_text(encoding="utf-8")
        forbidden = (
            "readme_justify_format",
            "readme_svg_overwrite",
            "loc_dot_padding",
            "stats_row_width",
            "_ORIGINAL_JUSTIFY_FORMAT",
            "_ORIGINAL_SVG_OVERWRITE",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertNotIn(name, source)
```

- [ ] **Step 2: Run the wrapper test and verify it fails against the current file**

Run:

```bash
python -m unittest tests.test_alignment.WrapperSeparationTests -v
```

Expected: FAIL because those alignment wrappers still exist.

- [ ] **Step 3: Simplify `generate_readme.py`**

Remove the alignment-specific import, constants, and functions. Keep the public repository fallback logic unchanged.

The final `main()` must be exactly equivalent to:

```python
def main():
    today.graph_repos_stars = actions_safe_repo_stats
    today.main()
```

- [ ] **Step 4: Add the test step to GitHub Actions**

Insert after dependency installation and before `Update README file`:

```yaml
      - name: Run tests
        run: python -m unittest discover -s tests -p "test_*.py" -v
```

Do not change the checkout, Python version, dependency installation, environment variables, commit identity, schedule, or push behavior.

- [ ] **Step 5: Run the full local test suite**

Run:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 6: Self-review checkpoint 4, tests and final source diff**

Review the complete diff and verify:

```text
[ ] generate_readme.py contains data-source compatibility logic only.
[ ] today.py contains the only alignment implementation.
[ ] Workflow tests run before SVG generation.
[ ] No dependency was added.
[ ] No profile value changed unexpectedly.
[ ] No API, cache, archive, or LOC-counting semantics changed.
[ ] No U+2014 exists in any modified source, test, workflow, plan, spec, or SVG file.
```

Run the repository-wide scan:

```bash
python - <<'PY'
from pathlib import Path
ignored = {".git"}
violations = []
for path in Path(".").rglob("*"):
    if not path.is_file() or any(part in ignored for part in path.parts):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if "\u2014" in text:
        violations.append(str(path))
assert not violations, violations
print("repository U+2014 scan passed")
PY
```

Expected: `repository U+2014 scan passed`.

- [ ] **Step 7: Commit Task 5**

```bash
git add generate_readme.py .github/workflows/build.yaml tests/test_alignment.py
git commit -m "ci: verify profile card alignment"
```

---

### Task 6: Stress-test both themes and verify the post-workflow result

**Files:**
- Modify only if a test exposes a real defect: `today.py`, `tests/test_alignment.py`, `dark_mode.svg`, `light_mode.svg`
- No planned content changes outside those files.

**Interfaces:**
- Consumes: all final alignment functions and template ids.
- Produces: evidence that current, short, long, and overflow values behave correctly in both themes.

- [ ] **Step 1: Add an end-to-end local rendering test using temporary SVG copies**

Append:

```python
import tempfile


class EndToEndRenderTests(unittest.TestCase):
    def render_copy(self, source_path, values):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / source_path.name
            target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            today.svg_overwrite(target, **values)
            return target.read_text(encoding="utf-8")

    def test_both_themes_render_without_network_and_without_u2014(self):
        values = {
            "age_data": "15 years, 10 months, 13 days",
            "commit_data": 100000,
            "star_data": 1234,
            "repo_data": 123,
            "contrib_data": 987,
            "follower_data": 100000,
            "loc_data": ["1,234,567", "765,432", "469,135"],
        }
        for source in TEMPLATE_PATHS:
            with self.subTest(source=source):
                rendered = self.render_copy(source, values)
                self.assertNotIn("\u2014", rendered)
                self.assertIn("100,000", rendered)
                self.assertIn("1.2M", rendered)
                self.assertIn("765.4K", rendered)
```

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 3: Run a syntax check on both Python entry points and the tests**

Run:

```bash
python -m py_compile today.py generate_readme.py tests/test_alignment.py
```

Expected: no output and exit status 0.

- [ ] **Step 4: Run a final repository U+2014 scan**

Use the exact scan from Task 5.

Expected: zero violations.

- [ ] **Step 5: Final self-review before claiming implementation complete**

Check:

```text
[ ] Spec requirement 1 maps to SIMPLE_ROW_SPECS plus align_simple_rows.
[ ] Spec requirement 2 maps to PROFILE_ROW_WIDTH = 60.
[ ] Spec requirement 3 maps to max(1, requested_width).
[ ] Spec requirement 4 maps to align_stats_rows.
[ ] Spec requirements 5 and 6 map to align_loc_row.
[ ] Spec requirement 7 is covered by shared ids and tests for both themes.
[ ] Spec requirement 8 is covered by value-node ids plus runtime recalculation.
[ ] Spec requirement 9 is covered by ASCII separators and repository scans.
[ ] Missing ids raise a descriptive ValueError.
[ ] generate_readme.py contains no rendering algorithm.
[ ] No unrelated profile content changed.
```

- [ ] **Step 6: Push or fast-forward `main` and allow the existing push-triggered workflow to run**

For normal Git execution:

```bash
git push origin main
```

For inline GitHub connector execution, apply the task commits to `main` with fast-forward ref updates only. Do not force-push.

- [ ] **Step 7: Verify the GitHub Actions-generated commit after the workflow finishes**

Check that the workflow succeeds and that its `Updated README` commit preserves:

```text
[ ] Both SVGs contain the same alignment ids.
[ ] Both SVGs contain only ASCII hyphen separators.
[ ] All current simple rows end at visible width 60.
[ ] Repos and Commits left regions target width 34.
[ ] Complete Repos, Commits, and LOC rows target visible width 60 when current values fit.
[ ] loc_del_dots remains empty.
[ ] No old hardcoded simple-row dot counts return.
[ ] No U+2014 returns.
```

- [ ] **Step 8: If the workflow exposes a defect, fix only the failing invariant, rerun the full suite, repeat the self-review, and verify the next workflow run**

Do not broaden scope during this step. Any unrelated cleanup belongs in a separate change.

---

## Plan Self-Review Record

### Spec coverage

Every requirement in `docs/superpowers/specs/2026-08-14-profile-card-alignment-design.md` is mapped to Tasks 1 through 6. No design requirement is left without an implementation or verification step.

### Placeholder scan

This plan contains no `TBD`, no deferred implementation markers, and no generic instructions such as "add tests" without concrete test bodies and commands.

### Type and interface consistency

The plan consistently uses these names across all tasks:

```text
PROFILE_ROW_WIDTH
STATS_LEFT_COLUMN_WIDTH
STATS_SEPARATOR
SIMPLE_ROW_SPECS
require_svg_element
svg_visible_text
build_dot_leader
set_aligned_dots
replace_display_value
align_simple_rows
stats_separator
align_stats_rows
align_loc_row
svg_overwrite
```

No later task refers to an interface under a different name.

### Execution choice

The requested execution mode is Inline Execution. After plan approval, use `superpowers:executing-plans` and execute this plan in the current session with review checkpoints between batches.