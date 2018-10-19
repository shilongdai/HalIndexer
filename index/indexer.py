import unittest

from data.web import PageDocument


class Indexer:
	"""
	A indexer that accepts page information from a web crawler and index it based on the idea presented in the paper
	The Anatomy of a Large-Scale Hypertextual Web Search Engine. Currently, it is not thread safe.
	"""

	def load(self):
		pass

	def index(self, data):
		pass

	def search_by_keywords(self, keywords):
		return []

	def close(self):
		pass


class TestIndexer(unittest.TestCase):

	@staticmethod
	def load_indexer():
		indexer = Indexer()
		indexer.load()
		return indexer

	@staticmethod
	def create_simple_multipage_data():
		headers1 = ["Page 1 test"]
		texts1 = "This should be the highest ranked by page rank", "Welcome to page 1"
		page1 = PageDocument(doc_id = 3, title = "Page 1", checksum = "12345", url = "https://www.page1.com",
		                     texts = texts1, headers = headers1)

		headers2 = ["Page 2 test", "References"]
		texts2 = "This should be the second ranked by page rank", "Welcome to page 2", "Page one is great"
		anchors2 = ["https://www.page1.com"]
		page2 = PageDocument(doc_id = 1, title = "Page 2", checksum = "67890", url = "https://www.page2.com",
		                     texts = texts2, anchors = anchors2, headers = headers2)

		headers3 = ["Page 3 test", "References"]
		texts3 = "This should be the third ranked by page rank", "Welcome to page 3", "Page two is great", "Page one is great"
		anchors3 = ["https://www.page2.com", "https://www.page1.com"]
		page3 = PageDocument(doc_id = 2, title = "Page 3", checksum = "09876", url = "https://www.page3.com",
		                     texts = texts3, anchors = anchors3, headers = headers3)
		return page1, page2, page3

	def test_single_entry(self):
		indexer = self.load_indexer()
		anchors = "https://www.example.com", "https://www.facebook.com"
		headers = "Go to example", "Like on facebook"
		texts = "This is a page used to test the indexer", "If you like this page, like on Facebook"
		page = PageDocument(doc_id = 1, title = "Test Page", checksum = "12345", url = "https://www.test.com",
		                    anchors = anchors, texts = texts, headers = headers)
		indexer.index(page)
		query_result = indexer.search_by_keywords("test")
		self.assertEqual(1, len(query_result), "search_by_keywords did not return the single page that it should match")
		self.assertEqual(1, query_result[0], "search_by_keywords did not maintain the id")
		indexer.close()

	def test_multiple_entry_with_single_word_query(self):
		indexer = self.load_indexer()
		pages = self.create_simple_multipage_data()
		indexer.index(pages)
		query_result = indexer.search_by_keywords("Page")
		self.assertEqual(3, len(query_result), "search_by_keywords did not return the pages that it should match")
		self.assertEqual(3, query_result[0], "The page Page 1 should be ranked first")
		self.assertEqual(1, query_result[1], "The page Page 2 should be ranked second")
		self.assertEqual(2, query_result[3], "The page Page 3 should be ranked third")
		indexer.close()

	def test_persistence(self):
		indexer = self.load_indexer()
		page = PageDocument(doc_id = 1, title = "Test persistence", checksum = "3782", url = "https://www.test-persistence.com")
		indexer.index(page)
		indexer.close()
		indexer = self.load_indexer()
		query_result = indexer.search_by_keywords("persistence")
		self.assertEqual(1, len(query_result), "Failed to persist")
		self.assertEqual(1, query_result[0], "Failed to maintain integrity")
