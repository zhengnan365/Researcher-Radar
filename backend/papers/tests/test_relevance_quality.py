from django.test import TestCase

from papers.models import Keyword, Paper, ResearchDirection, RssSource
from papers.services.relevance_scorer import score_paper


class RelevanceQualityTests(TestCase):
    def make_paper(self, title, abstract="", source=None):
        return Paper.objects.create(
            title=title,
            abstract=abstract,
            source=source,
            dedup_key=Paper.build_dedup_key(title=title),
        )

    def test_short_ascii_keyword_does_not_match_inside_another_word(self):
        Keyword.objects.create(keyword="air", weight=3)
        paper = self.make_paper("Chair design for offices")

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)
        self.assertEqual(paper.recommend_level, "low")

    def test_exclusion_keyword_suppresses_otherwise_high_score(self):
        Keyword.objects.create(keyword="battery", weight=3)
        Keyword.objects.create(keyword="retraction", is_exclusion=True)
        paper = self.make_paper("Battery recycling retraction analysis")

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)
        self.assertEqual(paper.recommend_level, "low")
        self.assertEqual(paper.score_detail["exclusion"], "retraction")

    def test_source_direction_alone_is_not_relevance_evidence(self):
        direction = ResearchDirection.objects.create(name="Storage")
        source = RssSource.objects.create(name="Broad journal", url="https://example.org/rss")
        paper = self.make_paper("Unrelated article", source=source)

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)
        self.assertEqual(paper.recommend_level, "low")

    def test_correction_notice_is_not_recommended_as_research(self):
        Keyword.objects.create(keyword="battery", weight=3)
        paper = self.make_paper("Correction: battery recycling study")

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)
        self.assertEqual(paper.score_detail["exclusion"], "publication_type")

    def test_journal_name_alone_does_not_recommend_paper(self):
        Keyword.objects.create(keyword="energy", weight=3)
        paper = self.make_paper("Unrelated ecology study")
        paper.journal = "Energy"
        paper.save(update_fields=["journal"])

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)

    def test_alias_matches_title_as_positive_evidence(self):
        Keyword.objects.create(keyword="proton exchange membrane", aliases="PEMFC")
        paper = self.make_paper("PEMFC catalyst durability")

        score_paper(paper)

        self.assertGreater(paper.recommend_score, 0)

    def test_direction_name_in_journal_is_not_evidence(self):
        ResearchDirection.objects.create(name="Energy")
        paper = self.make_paper("Urban ecology study")
        paper.journal = "Energy"
        paper.save(update_fields=["journal"])

        score_paper(paper)

        self.assertEqual(paper.recommend_score, 0)

    def test_source_bonus_requires_match_to_its_direction(self):
        storage = ResearchDirection.objects.create(name="Storage")
        solar = ResearchDirection.objects.create(name="Solar")
        Keyword.objects.create(keyword="solar", direction=solar)
        source = RssSource.objects.create(name="Broad journal", url="https://example.org/feed")
        paper = self.make_paper("Solar panel manufacturing", source=source)

        score_paper(paper)

        self.assertNotIn("source_direction", [item["type"] for item in paper.score_detail["items"]])
