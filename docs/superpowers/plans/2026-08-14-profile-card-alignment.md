# Profile Card Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual SVG dot counts and LOC-specific spacing patches with one reusable alignment engine that keeps every profile row aligned automatically when values change.

**Architecture:** Keep `dark_mode.svg` and `light_mode.svg` as visual templates. Give every aligned value and dot leader a stable id, then let `today.py` calculate all padding from visible text. Use one 60-character row width for the card, retain a 34-character left target for the two-column GitHub Stats rows, and remove all rendering overrides from `generate_readme.py`.

**Tech Stack:** Python 3.12, standard-library `unittest`, `lxml`, SVG/XML, GitHub Actions.

## Global Constraints

- Preserve current colors, font, coordinates, ASCII art, profile field content, GitHub statistics semantics, and LOC calculation.
- Do not move full SVG generation into Python.
- Both SVG themes must expose identical alignment ids.
- Normal profile rows target exactly 60 visible monospace characters when their values fit.
- The left part of `Repos` and `Commits` targets exactly 34 visible characters before ` |  `.
- Overflow must keep one separating space and extend right instead of creating negative padding.
- LOC must render `, -VALUE`, never `, . -VALUE`.
- The LOC final `)` targets column 60 when the row fits.
- No U+2014 character may exist in any file modified by this work, including comments, docstrings, Markdown, Python, tests, YAML, and SVG.
- Replace the three current decorative section separators with ASCII hyphens only.
- Tests must use no network access and no new dependency.
- Use `unittest`; `cache/requirements.txt` remains unchanged.

## File Map

Create:

```text
tests/__init__.py
tests/test_alignment.py
```

Modify:

```text
today.py
generate_readme.py
dark_mode.svg
light_mode.svg
.github/workflows/build.yaml
```

Do not modify `README.md` or `cache/requirements.txt` unless verification reveals an actual dependency, which is not expected.

---

### Task 1: Add pure alignment primitives with TDD

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_alignment.py`
- Modify: `today.py:20-45, 520-620`

**Interfaces:**
- Produces `PROFILE_ROW_WIDTH = 60`
- Produces `STATS_LEFT_COLUMN_WIDTH = 34`
- Produces `STATS_SEPARATOR = " |  "`
- Produces `require_svg_element(root, element_id)`
- Produces `svg_visible_text(element) -> str`
- Produces `build_dot_leader(width: int) -> str`
- Produces `set_aligned_dots(root, dots_id, prefix_text, value_text, suffix_text="", target_width=PROFILE_ROW_WIDTH) -> int`

- [ ] **Step 1: Create the test package and failing primitive tests**

Create `tests/__init__.py` with:

```python
"""Tests for the profile README generator."""
```

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

    def test_visible_text_reads_nested_anchor(self):
        root = fromstring(
            "<svg><tspan id='value'>before<a>vikbg.github.io/portfolio</a>after</tspan></svg>"
        )
        value = today.require_svg_element(root, "value")
        self.assertEqual(
            today.svg_visible_text(value),
            "beforevikbg.github.io/portfolioafter",
        )


class GenericAlignmentTests(unittest.TestCase):
    def make_root(self):
        return fromstring("<svg><tspan id='dots'></tspan></svg>")

    def test_short_value_gets_more_padding(self):
        root = self.make_root()
        width = today.set_aligned_dots(root, "dots", ". Example:", "x", target_width=20)
        dots = today.require_svg_element(root, "dots").text
        self.assertEqual(width, 20)
        self.assertEqual(len(dots), 9)

    def test_long_value_gets_less_padding(self):
        short_root = self.make_root()
        long_root = self.make_root()
        today.set_aligned_dots(short_root, "dots", ". Example:", "x", target_width=30)
        today.set_aligned_dots(long_root, "dots", ". Example:", "abcdefghij", target_width=30)
        short_dots = today.require_svg_element(short_root, "dots").text
        long_dots = today.require_svg_element(long_root, "dots").text
        self.assertGreater(len(short_dots), len(long_dots))

    def test_overflow_keeps_one_space(self):
        root = self.make_root()
        width = today.set_aligned_dots(
            root,
            "dots",
            ". VeryLongLabel:",
            "value-that-is-longer-than-the-target",
            target_width=20,
        )
        self.assertEqual(today.require_svg_element(root, "dots").text, " ")
        self.assertGreater(width, 20)
```

- [ ] **Step 2: Run tests and confirm the expected failure**

```bash
python -m unittest tests.test_alignment.DotLeaderTests tests.test_alignment.GenericAlignmentTests -v
```

Expected: FAIL because the new helper functions do not exist yet.

- [ ] **Step 3: Replace old visual width constants with layout constants**

In `today.py`, replace:

```python
AGE_DATA_WIDTH = 49
COMMIT_DATA_WIDTH = 22
LOC_DATA_WIDTH = 25
FOLLOWER_DATA_WIDTH = 10
REPO_DATA_WIDTH = 6
STAR_DATA_WIDTH = 14
STATS_SECONDARY_COLUMN_WIDTH = 34
STATS_SECONDARY_SEPARATOR = " |  "
```

with:

```python
PROFILE_ROW_WIDTH = 60
STATS_LEFT_COLUMN_WIDTH = 34
STATS_SEPARATOR = " |  "
```

- [ ] **Step 4: Add the primitive helpers**

Add to `today.py`:

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

- [ ] **Step 5: Run Task 1 tests**

```bash
python -m unittest tests.test_alignment.DotLeaderTests tests.test_alignment.GenericAlignmentTests -v
```

Expected: PASS.

- [ ] **Step 6: Self-review 1**

Verify all points:

```text
[ ] build_dot_leader is the only repeated-dot constructor.
[ ] PROFILE_ROW_WIDTH exists once and equals 60.
[ ] STATS_LEFT_COLUMN_WIDTH exists once and equals 34.
[ ] Overflow produces exactly one separator space.
[ ] Missing alignment ids raise ValueError.
[ ] No U+2014 exists in today.py or either test file.
```

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in (Path("today.py"), Path("tests/__init__.py"), Path("tests/test_alignment.py")):
    assert "\u2014" not in path.read_text(encoding="utf-8"), path
print("Task 1 review passed")
PY
```

- [ ] **Step 7: Commit Task 1**

```bash
git add today.py tests/__init__.py tests/test_alignment.py
git commit -m "test: add profile alignment primitives"
```

---

### Task 2: Migrate SVG templates and align every simple row

**Files:**
- Modify: `dark_mode.svg:46-70`
- Modify: `light_mode.svg:46-70`
- Modify: `today.py:25-60, 540-660`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Produces `SIMPLE_ROW_SPECS`
- Produces `replace_display_value(root, element_id, value) -> str`
- Produces `align_simple_rows(root) -> None`

Required simple id pairs:

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

- [ ] **Step 1: Add failing template and simple-row tests**

Append to `tests/test_alignment.py`:

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


class TemplateTests(unittest.TestCase):
    def ids_for(self, path):
        root = parse(path).getroot()
        return {node.get("id") for node in root.iter() if node.get("id")}

    def test_themes_have_required_ids(self):
        for path in TEMPLATE_PATHS:
            with self.subTest(path=path):
                self.assertTrue(SIMPLE_IDS.issubset(self.ids_for(path)))

    def test_themes_have_identical_ids(self):
        self.assertEqual(self.ids_for(TEMPLATE_PATHS[0]), self.ids_for(TEMPLATE_PATHS[1]))

    def test_svg_files_have_no_u2014(self):
        for path in TEMPLATE_PATHS:
            with self.subTest(path=path):
                self.assertNotIn("\u2014", path.read_text(encoding="utf-8"))


class SimpleRowTests(unittest.TestCase):
    def row_width(self, root, dots_id, value_id, prefix):
        dots = today.require_svg_element(root, dots_id).text or ""
        value = today.svg_visible_text(today.require_svg_element(root, value_id))
        return len(prefix) + len(dots) + len(value)

    def test_current_simple_rows_target_60_in_both_themes(self):
        for path in TEMPLATE_PATHS:
            root = parse(path).getroot()
            today.align_simple_rows(root)
            for dots_id, value_id, prefix in today.SIMPLE_ROW_SPECS:
                with self.subTest(path=path, dots_id=dots_id):
                    self.assertEqual(
                        self.row_width(root, dots_id, value_id, prefix),
                        today.PROFILE_ROW_WIDTH,
                    )

    def test_longer_language_value_reduces_padding(self):
        root = parse(TEMPLATE_PATHS[0]).getroot()
        today.align_simple_rows(root)
        before = today.require_svg_element(root, "languages_application_dots").text or ""
        value = today.require_svg_element(root, "languages_application_value")
        value.text = "Python, TypeScript, C#, JavaScript"
        today.align_simple_rows(root)
        after = today.require_svg_element(root, "languages_application_dots").text or ""
        self.assertLess(len(after), len(before))

    def test_long_email_overflows_with_one_space(self):
        root = parse(TEMPLATE_PATHS[0]).getroot()
        today.require_svg_element(root, "email_value").text = (
            "a-very-long-email-address-that-exceeds-the-normal-row-width@example.com"
        )
        today.align_simple_rows(root)
        self.assertEqual(today.require_svg_element(root, "email_dots").text, " ")
```

- [ ] **Step 2: Run tests and confirm expected failures**

```bash
python -m unittest tests.test_alignment.TemplateTests tests.test_alignment.SimpleRowTests -v
```

Expected: FAIL because ids, ASCII separators, `SIMPLE_ROW_SPECS`, and `align_simple_rows` are not implemented yet.

- [ ] **Step 3: Add the same ids to both SVG themes**

Put each `*_dots` id on its dot-leader `tspan`, and each `*_value` id on the matching value `tspan`. Keep `age_data_dots` and `age_data` as they already exist.

For the portfolio row, use:

```xml
<tspan class="cc" id="portfolio_dots"> ................ </tspan><tspan class="value" id="portfolio_value"><a href="https://vikbg.github.io/portfolio">vikbg.github.io/portfolio</a></tspan>
```

Do not move the id onto the nested anchor.

- [ ] **Step 4: Replace the three decorative separators with ASCII hyphens**

Use exactly these 60-character visible lines in both themes:

```text
viktor@serhiienko ------------------------------------------
- Contact --------------------------------------------------
- GitHub Stats ---------------------------------------------
```

That is 42 hyphens after the profile name, 50 after `- Contact`, and 45 after `- GitHub Stats`.

- [ ] **Step 5: Add the simple-row configuration and renderer to `today.py`**

Add:

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


def replace_display_value(root, element_id, value):
    text = format_display_text(value)
    require_svg_element(root, element_id).text = text
    return text


def align_simple_rows(root):
    for dots_id, value_id, prefix_text in SIMPLE_ROW_SPECS:
        value_text = svg_visible_text(require_svg_element(root, value_id))
        set_aligned_dots(root, dots_id, prefix_text, value_text)
```

- [ ] **Step 6: Run Task 2 tests**

```bash
python -m unittest tests.test_alignment.TemplateTests tests.test_alignment.SimpleRowTests -v
```

Expected: PASS.

- [ ] **Step 7: Self-review 2**

Verify:

```text
[ ] Both themes expose identical ids.
[ ] Every simple row uses one dot id and one value id.
[ ] Current simple rows calculate to 60 characters in both themes.
[ ] Long static values reduce dots automatically.
[ ] Overflow uses one separating space.
[ ] Portfolio href and visible text are unchanged.
[ ] No profile value content changed.
[ ] Colors, coordinates, font, and ASCII art are unchanged.
[ ] No U+2014 exists in either SVG.
```

- [ ] **Step 8: Commit Task 2**

```bash
git add today.py dark_mode.svg light_mode.svg tests/test_alignment.py
git commit -m "feat: align simple profile rows dynamically"
```

---

### Task 3: Unify GitHub Stats and LOC alignment, then remove wrapper patches

**Files:**
- Modify: `today.py:520-650`
- Modify: `generate_readme.py:1-170`
- Modify: `tests/test_alignment.py`

**Interfaces:**
- Produces `stats_separator(current_width: int) -> str`
- Produces `align_stats_rows(root) -> None`
- Produces `align_loc_row(root) -> None`
- Removes `justify_format`, `build_dot_string`, `secondary_stat_gap`, `repo_stats_left_width`, and `commit_stats_left_width`
- Removes alignment-only code from `generate_readme.py`

- [ ] **Step 1: Add failing stats, LOC, and wrapper-separation tests**

Append:

```python
class StatsTests(unittest.TestCase):
    def parse_dark(self):
        return parse(TEMPLATE_PATHS[0]).getroot()

    def set_value(self, root, element_id, value):
        today.require_svg_element(root, element_id).text = today.format_display_text(value)

    def repos_width(self, root):
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

    def commits_width(self, root):
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

    def loc_width(self, root):
        net = today.svg_visible_text(today.require_svg_element(root, "loc_data"))
        added = today.svg_visible_text(today.require_svg_element(root, "loc_add"))
        deleted = today.svg_visible_text(today.require_svg_element(root, "loc_del"))
        dots = today.require_svg_element(root, "loc_data_dots").text or ""
        return len(f". GitHub LOC:{dots}{net} ( +{added}, -{deleted} )")

    def test_current_stats_rows_target_60(self):
        root = self.parse_dark()
        today.align_stats_rows(root)
        today.align_loc_row(root)
        self.assertEqual(self.repos_width(root), 60)
        self.assertEqual(self.commits_width(root), 60)
        self.assertEqual(self.loc_width(root), 60)

    def test_commit_and_follower_values_reflow(self):
        for commits, followers in ((9, 9), (99, 99), (999, 999), (1000, 1000), (100000, 100000)):
            root = self.parse_dark()
            self.set_value(root, "commit_data", commits)
            self.set_value(root, "follower_data", followers)
            today.align_stats_rows(root)
            self.assertGreaterEqual(self.commits_width(root), 60)

    def test_loc_reflows_without_deletion_dots(self):
        root = self.parse_dark()
        self.set_value(root, "loc_data", "1,234,567")
        self.set_value(root, "loc_add", "1.23M")
        self.set_value(root, "loc_del", "765.4K")
        today.align_loc_row(root)
        self.assertEqual(self.loc_width(root), 60)
        self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")


class WrapperTests(unittest.TestCase):
    def test_generate_readme_has_no_alignment_wrapper(self):
        source = Path("generate_readme.py").read_text(encoding="utf-8")
        for name in (
            "readme_justify_format",
            "readme_svg_overwrite",
            "loc_dot_padding",
            "stats_row_width",
            "_ORIGINAL_JUSTIFY_FORMAT",
            "_ORIGINAL_SVG_OVERWRITE",
        ):
            with self.subTest(name=name):
                self.assertNotIn(name, source)
```

- [ ] **Step 2: Run the new tests and confirm expected failures**

```bash
python -m unittest tests.test_alignment.StatsTests tests.test_alignment.WrapperTests -v
```

Expected: FAIL because the new core stats functions are missing and the wrapper still contains alignment code.

- [ ] **Step 3: Add the stats separator and core stats renderer**

Add:

```python
def stats_separator(current_width):
    return (" " * max(0, STATS_LEFT_COLUMN_WIDTH - current_width)) + STATS_SEPARATOR


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
    repo_prefix = (
        ". Repos:"
        + (require_svg_element(root, "repo_data_dots").text or "")
        + repo_text
        + repo_suffix
        + repo_gap
        + "Stars:"
    )
    set_aligned_dots(root, "star_data_dots", repo_prefix, star_text)

    commit_left_width = set_aligned_dots(
        root,
        "commit_data_dots",
        ". Commits:",
        commit_text,
        target_width=STATS_LEFT_COLUMN_WIDTH,
    )
    commit_gap = stats_separator(commit_left_width)
    require_svg_element(root, "commit_stats_gap").text = commit_gap
    commit_prefix = (
        ". Commits:"
        + (require_svg_element(root, "commit_data_dots").text or "")
        + commit_text
        + commit_gap
        + "Followers:"
    )
    set_aligned_dots(root, "follower_data_dots", commit_prefix, follower_text)
```

- [ ] **Step 4: Add LOC alignment using the same primitive**

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
    )
    require_svg_element(root, "loc_del_dots").text = ""
```

- [ ] **Step 5: Refactor `svg_overwrite` into one replace-then-align pass**

Use this body:

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

Delete the obsolete per-field alignment helpers after confirming no call sites remain:

```text
justify_format
build_dot_string
secondary_stat_gap
repo_stats_left_width
commit_stats_left_width
```

- [ ] **Step 6: Remove rendering overrides from `generate_readme.py`**

Remove:

```text
from lxml.etree import parse
_ORIGINAL_JUSTIFY_FORMAT
_ORIGINAL_SVG_OVERWRITE
readme_justify_format
stats_row_width
loc_dot_padding
readme_svg_overwrite
```

Keep all GitHub Actions-safe data acquisition code unchanged. Final `main()`:

```python
def main():
    today.graph_repos_stars = actions_safe_repo_stats
    today.main()
```

- [ ] **Step 7: Run Task 3 tests and then the full suite**

```bash
python -m unittest tests.test_alignment.StatsTests tests.test_alignment.WrapperTests -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 8: Self-review 3**

Verify:

```text
[ ] Repos and Commits left segments target 34 characters.
[ ] Full Repos, Commits, and LOC rows target 60 when values fit.
[ ] Stats with longer counts recalculate padding automatically.
[ ] LOC uses set_aligned_dots, not a separate dot builder.
[ ] loc_del_dots is always empty after rendering.
[ ] generate_readme.py contains data-source compatibility only.
[ ] No obsolete per-field width constant remains.
[ ] No duplicate repeated-dot implementation remains.
[ ] No U+2014 exists in modified files.
```

- [ ] **Step 9: Commit Task 3**

```bash
git add today.py generate_readme.py tests/test_alignment.py
git commit -m "refactor: unify profile stats alignment"
```

---

### Task 4: Add CI coverage, stress rendering, and perform final reviews

**Files:**
- Modify: `.github/workflows/build.yaml:18-30`
- Modify: `tests/test_alignment.py`
- Modify other implementation files only if a test proves a defect.

**Interfaces:**
- Consumes final renderer from Tasks 1 through 3.
- Produces workflow-level regression protection.

- [ ] **Step 1: Add a local end-to-end rendering test**

Append imports:

```python
import tempfile
```

Append:

```python
class EndToEndTests(unittest.TestCase):
    def render_copy(self, source, values):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / source.name
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            today.svg_overwrite(target, **values)
            return target.read_text(encoding="utf-8")

    def test_both_themes_render_large_values_without_u2014(self):
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
                self.assertIn("1.23M", rendered)
                self.assertIn("765.4K", rendered)
```

- [ ] **Step 2: Run the complete suite and Python syntax checks**

```bash
python -m unittest discover -s tests -p "test_*.py" -v
python -m py_compile today.py generate_readme.py tests/test_alignment.py
```

Expected: all tests PASS and `py_compile` exits 0 with no output.

- [ ] **Step 3: Add tests to the existing GitHub Actions workflow**

Insert immediately after dependency installation:

```yaml
      - name: Run tests
        run: python -m unittest discover -s tests -p "test_*.py" -v
```

Do not change the Python version, dependency installation, workflow schedule, secrets, commit identity, or push command.

- [ ] **Step 4: Run the full suite again after workflow editing**

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS.

- [ ] **Step 5: Repository-wide U+2014 scan**

Run:

```bash
python - <<'PY'
from pathlib import Path
violations = []
for path in Path(".").rglob("*"):
    if not path.is_file() or ".git" in path.parts:
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

- [ ] **Step 6: Self-review 4, final diff and spec coverage**

Check all items:

```text
[ ] Every simple row is represented in SIMPLE_ROW_SPECS.
[ ] Every simple row uses a runtime dot id and value id.
[ ] Both themes have identical alignment ids.
[ ] Current fitting rows end at column 60.
[ ] Repos and Commits left regions target column 34.
[ ] LOC final parenthesis targets column 60 when it fits.
[ ] Overflow remains readable with one separating space.
[ ] Missing ids raise ValueError.
[ ] LOC deletion never receives dot padding.
[ ] No profile content, color, coordinate, font, or stats meaning changed.
[ ] generate_readme.py contains no alignment implementation.
[ ] Workflow runs tests before generation.
[ ] No U+2014 exists anywhere in the checked repository tree.
```

- [ ] **Step 7: Commit Task 4**

```bash
git add .github/workflows/build.yaml tests/test_alignment.py
git commit -m "ci: verify profile card alignment"
```

- [ ] **Step 8: Push or fast-forward `main` without force**

Normal Git execution:

```bash
git push origin main
```

Inline GitHub connector execution must use normal fast-forward updates only. Do not force-push.

- [ ] **Step 9: Post-workflow self-review 5**

After the push-triggered workflow finishes, fetch the generated `dark_mode.svg` and `light_mode.svg` from `main` and verify:

```text
[ ] Workflow succeeded.
[ ] Both themes still expose identical alignment ids.
[ ] Current simple rows calculate to width 60.
[ ] Repos and Commits left regions calculate to width 34 when fitting.
[ ] Full Repos, Commits, and LOC rows calculate to width 60 when fitting.
[ ] loc_del_dots is empty.
[ ] ASCII separators remain in place.
[ ] U+2014 did not return.
[ ] The workflow did not restore old hardcoded dot leaders or wrapper behavior.
```

If a real invariant fails, fix only that invariant, rerun the full suite, rerun the relevant self-review, and verify the next workflow result before completion.

---

## Plan Self-Review Record

### Spec coverage

All requirements from `docs/superpowers/specs/2026-08-14-profile-card-alignment-design.md` map to Tasks 1 through 4. Static rows, dynamic rows, two-column stats, LOC formatting, overflow, missing ids, theme parity, CI, and U+2014 validation all have concrete implementation and test steps.

### Placeholder scan

The plan contains no `TBD`, no deferred implementation marker, and no instruction to add unspecified tests or error handling. Code-producing steps include exact interfaces and representative final code.

### Type and name consistency

The same interface names are used throughout:

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

### Numerical consistency

The current right-side profile rows are 60 visible monospace characters wide. The current two-column left segments are 34 characters wide. The end-to-end compact LOC expectation uses `1.23M` for `1,234,567`, matching the existing `format_compact_number()` two-decimal behavior for million-scale values.

### Execution mode

The requested mode is Inline Execution. After user approval of this plan, invoke `superpowers:executing-plans` and execute the plan in this conversation with review checkpoints between batches.