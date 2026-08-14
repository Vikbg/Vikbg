import shutil
import tempfile
import unittest
from pathlib import Path

from lxml.etree import fromstring, parse

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


class StatsAlignmentTests(unittest.TestCase):
    def parse_dark(self):
        return parse(TEMPLATE_PATHS[0]).getroot()

    def set_value(self, root, element_id, value):
        today.require_svg_element(root, element_id).text = value

    def repos_width(self, root):
        repos = today.svg_visible_text(today.require_svg_element(root, "repo_data"))
        contrib = today.svg_visible_text(today.require_svg_element(root, "contrib_data"))
        stars = today.svg_visible_text(today.require_svg_element(root, "star_data"))
        repo_dots = today.require_svg_element(root, "repo_data_dots").text or ""
        gap = today.require_svg_element(root, "repo_stats_gap").text or ""
        star_dots = today.require_svg_element(root, "star_data_dots").text or ""
        return len(
            f". Repos:{repo_dots}{repos} {{Contributed: {contrib}}}"
            f"{gap}Stars:{star_dots}{stars}"
        )

    def commits_width(self, root):
        commits = today.svg_visible_text(today.require_svg_element(root, "commit_data"))
        followers = today.svg_visible_text(today.require_svg_element(root, "follower_data"))
        commit_dots = today.require_svg_element(root, "commit_data_dots").text or ""
        gap = today.require_svg_element(root, "commit_stats_gap").text or ""
        follower_dots = today.require_svg_element(root, "follower_data_dots").text or ""
        return len(
            f". Commits:{commit_dots}{commits}"
            f"{gap}Followers:{follower_dots}{followers}"
        )

    def loc_width(self, root):
        net = today.svg_visible_text(today.require_svg_element(root, "loc_data"))
        added = today.svg_visible_text(today.require_svg_element(root, "loc_add"))
        deleted = today.svg_visible_text(today.require_svg_element(root, "loc_del"))
        dots = today.require_svg_element(root, "loc_data_dots").text or ""
        return len(f". GitHub LOC:{dots}{net} ( +{added}, -{deleted} )")

    def test_repos_and_stars_target_60_for_small_and_large_counts(self):
        cases = (
            ("1", "1", "1"),
            ("99", "120", "999"),
            ("1,000", "12,345", "100,000"),
        )
        for repos, contrib, stars in cases:
            with self.subTest(repos=repos, contrib=contrib, stars=stars):
                root = self.parse_dark()
                self.set_value(root, "repo_data", repos)
                self.set_value(root, "contrib_data", contrib)
                self.set_value(root, "star_data", stars)
                today.align_stats_rows(root)
                self.assertEqual(self.repos_width(root), today.PROFILE_ROW_WIDTH)

    def test_commits_and_followers_target_60_across_digit_growth(self):
        for value in ("9", "99", "999", "1,000", "100,000"):
            with self.subTest(value=value):
                root = self.parse_dark()
                self.set_value(root, "commit_data", value)
                self.set_value(root, "follower_data", value)
                today.align_stats_rows(root)
                self.assertEqual(self.commits_width(root), today.PROFILE_ROW_WIDTH)

    def test_stats_overflow_stays_readable(self):
        root = self.parse_dark()
        self.set_value(root, "commit_data", "123,456,789,012,345")
        self.set_value(root, "follower_data", "987,654,321,098,765")
        today.align_stats_rows(root)
        self.assertGreater(self.commits_width(root), today.PROFILE_ROW_WIDTH)
        self.assertIn(" |  ", today.require_svg_element(root, "commit_stats_gap").text or "")

    def test_loc_row_targets_60_and_has_no_deletion_dots(self):
        root = self.parse_dark()
        today.align_loc_row(root)
        self.assertEqual(self.loc_width(root), today.PROFILE_ROW_WIDTH)
        self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")

    def test_loc_reflows_when_compact_values_change_length(self):
        root = self.parse_dark()
        self.set_value(root, "loc_data", "1,234,567")
        self.set_value(root, "loc_add", "1.23M")
        self.set_value(root, "loc_del", "765.4K")
        today.align_loc_row(root)
        self.assertEqual(self.loc_width(root), today.PROFILE_ROW_WIDTH)
        self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")


class RenderIntegrationTests(unittest.TestCase):
    def render_copy(self, source, values):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        target = Path(temp_dir.name) / source.name
        shutil.copyfile(source, target)
        today.svg_overwrite(target, **values)
        return parse(target).getroot(), target.read_text(encoding="utf-8")

    def row_width(self, root, dots_id, value_id, prefix):
        dots = today.require_svg_element(root, dots_id).text or ""
        value = today.svg_visible_text(today.require_svg_element(root, value_id))
        return len(prefix) + len(dots) + len(value)

    def stats_width(self, root, kind):
        helper = StatsAlignmentTests()
        if kind == "repos":
            return helper.repos_width(root)
        return helper.commits_width(root)

    def loc_width(self, root):
        return StatsAlignmentTests().loc_width(root)

    def test_svg_overwrite_aligns_every_group_and_dynamic_stat(self):
        values = {
            "age_data": "15 years, 11 months, 2 days",
            "commit_data": 1000,
            "star_data": 123,
            "repo_data": 42,
            "contrib_data": 108,
            "follower_data": 100000,
            "loc_data": ["1,234,567", "765,432", "469,135"],
        }
        for source in TEMPLATE_PATHS:
            with self.subTest(source=source):
                root, rendered = self.render_copy(source, values)
                for dots_id, value_id, prefix in today.SIMPLE_ROW_SPECS:
                    self.assertEqual(
                        self.row_width(root, dots_id, value_id, prefix),
                        today.PROFILE_ROW_WIDTH,
                    )
                self.assertEqual(self.stats_width(root, "repos"), today.PROFILE_ROW_WIDTH)
                self.assertEqual(self.stats_width(root, "commits"), today.PROFILE_ROW_WIDTH)
                self.assertEqual(self.loc_width(root), today.PROFILE_ROW_WIDTH)
                self.assertEqual(today.require_svg_element(root, "commit_data").text, "1,000")
                self.assertEqual(today.require_svg_element(root, "follower_data").text, "100,000")
                self.assertEqual(today.require_svg_element(root, "loc_add").text, "1.23M")
                self.assertEqual(today.require_svg_element(root, "loc_del").text, "765.4K")
                self.assertEqual(today.require_svg_element(root, "loc_del_dots").text or "", "")
                self.assertNotIn("\u2014", rendered)

    def test_missing_template_id_fails_render_clearly(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        target = Path(temp_dir.name) / "broken.svg"
        text = TEMPLATE_PATHS[0].read_text(encoding="utf-8").replace(' id="email_dots"', '', 1)
        target.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing required SVG element: email_dots"):
            today.svg_overwrite(
                target,
                "15 years, 11 months, 2 days",
                10,
                20,
                30,
                40,
                50,
                ["100", "20", "80"],
            )


class CleanupAndWorkflowTests(unittest.TestCase):
    def test_generate_readme_has_no_alignment_override_layer(self):
        source = Path("generate_readme.py").read_text(encoding="utf-8")
        forbidden = (
            "_ORIGINAL_JUSTIFY_FORMAT",
            "_ORIGINAL_SVG_OVERWRITE",
            "readme_justify_format",
            "readme_svg_overwrite",
            "loc_dot_padding",
            "from lxml.etree import parse",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertNotIn(name, source)

    def test_legacy_alignment_helpers_are_removed_from_today(self):
        for name in (
            "justify_format",
            "build_dot_string",
            "secondary_stat_gap",
            "repo_stats_left_width",
            "commit_stats_left_width",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(today, name))

    def test_workflow_runs_tests_before_generator(self):
        workflow = Path(".github/workflows/build.yaml").read_text(encoding="utf-8")
        test_command = "python -m unittest discover -s tests -v"
        generator_command = "python generate_readme.py"
        self.assertIn(test_command, workflow)
        self.assertLess(workflow.index(test_command), workflow.index(generator_command))

    def test_all_modified_target_files_have_no_u2014(self):
        paths = (
            Path("today.py"),
            Path("generate_readme.py"),
            Path("dark_mode.svg"),
            Path("light_mode.svg"),
            Path("tests/__init__.py"),
            Path("tests/test_alignment.py"),
            Path(".github/workflows/build.yaml"),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn("\u2014", path.read_text(encoding="utf-8"))
