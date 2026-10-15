from django.core.exceptions import ValidationError
from django.test import TestCase

from papers.models import Keyword, Paper, ResearchDirection, RssSource
from papers.services.keyword_matcher import classify_payload_keywords_and_directions
from papers.services.matching_engine import match_document
from papers.services.relevance_scorer import score_paper


class InterestScoringTests(TestCase):
    def make_paper(self, title, abstract="", raw_keywords="", source=None):
        return Paper.objects.create(
            title=title,
            abstract=abstract,
            raw_keywords=raw_keywords,
            source=source,
            dedup_key=Paper.build_dedup_key(title=title),
        )

    def test_direction_name_compatibility_and_weight_validation(self):
        direction = ResearchDirection.objects.create(name="储能")
        self.assertEqual(direction.name_cn, "储能")
        direction.name_cn = "储能系统"
        direction.save()
        direction.refresh_from_db()
        self.assertEqual(direction.name, "储能系统")
        direction.direction_weight = 6
        with self.assertRaises(ValidationError):
            direction.full_clean()

    def test_fetch_classification_uses_same_evidence_as_scoring(self):
        direction = ResearchDirection.objects.create(name="储能", direction_weight=5)
        keyword = Keyword.objects.create(keyword="battery storage", aliases="BESS", weight=5, direction=direction)
        source = RssSource.objects.create(name="Broad journal", url="https://example.org/feed")
        payload = {"title": "BESS operation", "abstract": "", "raw_keywords": ""}
        keywords, directions = classify_payload_keywords_and_directions(payload, source)
        self.assertEqual(keywords, [keyword])
        self.assertEqual(directions, [direction])
        paper = self.make_paper(payload["title"], source=source)
        score_paper(paper)
        self.assertEqual(list(paper.keywords.all()), keywords)
        self.assertEqual(list(paper.directions.all()), directions)
        self.assertEqual(paper.score_detail["keywords"][0]["score"], 15)

    def test_source_binding_and_journal_are_not_evidence(self):
        direction = ResearchDirection.objects.create(name="Storage")
        Keyword.objects.create(keyword="storage", direction=direction)
        source = RssSource.objects.create(name="Storage", url="https://example.org/rss", journal="Storage")
        payload = {"title": "Unrelated biology paper", "abstract": "", "raw_keywords": ""}
        self.assertEqual(classify_payload_keywords_and_directions(payload, source), ([], []))
        paper = self.make_paper(payload["title"], source=source)
        paper.journal = "Storage"
        score_paper(paper)
        self.assertEqual(paper.recommend_score, 0)

    def test_long_phrase_suppresses_nested_generic_keyword(self):
        Keyword.objects.create(keyword="energy storage", weight=3)
        Keyword.objects.create(keyword="battery energy storage system", weight=5)
        result = match_document(title="Battery energy storage system operation")
        self.assertEqual([match.keyword.keyword for match in result.keywords], ["battery energy storage system"])

    def test_bonus_cap_and_score_detail(self):
        direction = ResearchDirection.objects.create(name="储能", direction_weight=5, priority=5)
        Keyword.objects.create(keyword="battery storage", weight=5, direction=direction)
        paper = self.make_paper("Battery storage planning", abstract="Battery storage operation")
        score_paper(paper)
        detail = paper.score_detail
        self.assertEqual(detail["keyword_score"], 25)
        self.assertEqual(detail["bonus_cap"], 6.25)
        self.assertLessEqual(detail["direction_bonus"]["score"] + detail["field_bonus"], 6.25)
        self.assertGreater(detail["direction_bonus"]["score"], 0)
        self.assertGreater(detail["field_bonus"], 0)
        self.assertEqual(detail["final_score"], 31)
        self.assertEqual(paper.recommend_score, 31)

    def test_priority_does_not_change_score_and_irrelevant_stays_zero(self):
        direction = ResearchDirection.objects.create(name="储能", direction_weight=4, priority=1)
        Keyword.objects.create(keyword="battery", weight=4, direction=direction)
        paper = self.make_paper("Battery scheduling")
        score_paper(paper)
        original = paper.recommend_score
        direction.priority = 5
        direction.save()
        paper.relevance_override = "irrelevant"
        score_paper(paper)
        self.assertEqual(paper.system_recommend_score, original)
        self.assertEqual(paper.recommend_score, 0)

    def test_cross_domain_title_term_cannot_be_key_recommendation(self):
        Keyword.objects.create(keyword="thermal energy storage", weight=4)
        Keyword.objects.create(keyword="multi-objective optimization", weight=5)
        paper = self.make_paper(
            "Multi-objective optimization of airborne high-power laser thermal energy storage",
            abstract="This study evaluates thermal energy storage performance.",
        )
        score_paper(paper)
        self.assertEqual(paper.score_detail["key_demotion_match"], "airborne high-power laser")
        self.assertLess(paper.recommend_score, 30)
