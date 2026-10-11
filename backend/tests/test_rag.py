import unittest
from nexus_app.engine.rag import RAGPipelineEngine

class TestRAGPipeline(unittest.TestCase):
    def test_chunking_sliding_window(self):
        text = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10"
        chunks = RAGPipelineEngine.chunk_text(text, chunk_size=5, chunk_overlap=2)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("word1"))

    def test_semantic_query_retrieval(self):
        chunks = [
            {"id": "c1", "text_content": "Playwright is an automated browser tool for modern web testing and scraping."},
            {"id": "c2", "text_content": "PostgreSQL is an advanced relational database with powerful indexing."},
            {"id": "c3", "text_content": "Beautiful Soup provides idiomatic ways of navigating and searching HTML."}
        ]
        results = RAGPipelineEngine.query_chunks(chunks, query="browser automation testing", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "c1")
        self.assertGreater(results[0]["similarity_score"], 0.2)

if __name__ == "__main__":
    unittest.main()
