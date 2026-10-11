import unittest
from nexus_app.engine.extractor import ExtractorEngine

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Nexus Tech Blog - AI in 2026</title>
    <meta name="description" content="An in-depth review of autonomous web extraction.">
    <meta property="og:title" content="Nexus Tech Blog">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Autonomous Web Extraction",
        "author": "Dr. Alan Vance"
    }
    </script>
</head>
<body>
    <header>
        <h1 class="main-title">Autonomous Web Intelligence</h1>
        <p class="author">By Dr. Alan Vance</p>
        <span class="pub-date">October 11, 2026</span>
    </header>
    <div id="articles">
        <article class="post">
            <h2 class="post-title">Deep Learning scrapers</h2>
            <a class="read-more" href="/articles/1">Read Full Story</a>
            <span class="views">1,450 views</span>
        </article>
        <article class="post">
            <h2 class="post-title">Playwright Automation</h2>
            <a class="read-more" href="/articles/2">Read Full Story</a>
            <span class="views">3,200 views</span>
        </article>
    </div>
</body>
</html>
"""

class TestExtractorEngine(unittest.TestCase):
    def setUp(self):
        self.extractor = ExtractorEngine(SAMPLE_HTML, base_url="https://example.com")

    def test_metadata_extraction(self):
        meta = self.extractor.get_page_metadata()
        self.assertEqual(meta["title"], "Nexus Tech Blog - AI in 2026")
        self.assertEqual(meta["description"], "An in-depth review of autonomous web extraction.")
        self.assertEqual(meta["og:title"], "Nexus Tech Blog")

    def test_json_ld_extraction(self):
        schemas = self.extractor.get_json_ld()
        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["headline"], "Autonomous Web Extraction")
        self.assertEqual(schemas[0]["author"], "Dr. Alan Vance")

    def test_css_selector_text(self):
        title = self.extractor.extract_field("h1.main-title", selector_type="css", extract_type="text")
        self.assertEqual(title, "Autonomous Web Intelligence")

    def test_css_selector_multiple(self):
        posts = self.extractor.extract_field("h2.post-title", selector_type="css", is_multiple=True)
        self.assertEqual(len(posts), 2)
        self.assertIn("Deep Learning scrapers", posts)
        self.assertIn("Playwright Automation", posts)

    def test_attribute_extraction_with_url_resolution(self):
        link = self.extractor.extract_field("a.read-more", selector_type="css", extract_type="attr", attribute_name="href")
        self.assertEqual(link, "https://example.com/articles/1")

    def test_xpath_selector(self):
        xpath_title = self.extractor.extract_field("//h1[@class='main-title']", selector_type="xpath", extract_type="text")
        self.assertEqual(xpath_title, "Autonomous Web Intelligence")

if __name__ == "__main__":
    unittest.main()
