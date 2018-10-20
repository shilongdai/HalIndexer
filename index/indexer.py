import os
import shutil
import unittest

from data.web import Anchor
from data.web import PageDocument
from index.entry import ForwardIndexEntry
from index.entry import Hit
from index.entry import WordDictionaryEntry


def file_binary_search(file, target, comparator, entry_size, start, end):
	# seek to middle
	difference = end - start
	if difference % entry_size != 0:
		raise ValueError("The range start-end must be divisible by entry_size")
	if difference == 0:
		return False, None, start
	entry_count = difference // entry_size
	middle_count = entry_count // 2
	seek_position = start + (entry_size * middle_count)
	file.seek(seek_position, 0)
	entry = file.read(entry_size)
	# compare the target to the seeked entry
	comparison_result = comparator(target, entry)

	# do recursive binary search
	if comparison_result == 0:
		return True, entry, seek_position
	if comparison_result > 0:
		return file_binary_search(file, target, comparator, entry_size, seek_position + entry_size, end)
	else:
		return file_binary_search(file, target, comparator, entry_size, start, seek_position)


class WordDictionary:

	def __init__(self, path):
		self.path = path
		self._dictionary = dict()
		self.current_id = 0

	def load(self):
		if not os.path.isfile(self.path):
			with open(self.path, mode = "w"):
				pass

		dictionary_file = open(self.path, mode = "r")
		try:
			for line in dictionary_file:
				dic_entry = WordDictionaryEntry.unpack(line)
				self._dictionary[dic_entry.word] = dic_entry
				if dic_entry.word_id > self.current_id:
					self.current_id = dic_entry.word_id
		finally:
			dictionary_file.close()
			self.current_id += 1

	def close(self):
		dictionary_file = open(self.path, mode = "w")
		try:
			for entry in self._dictionary.values():
				dictionary_file.write(entry.pack() + '\n')
		finally:
			dictionary_file.close()

	def get_word_id(self, word):
		if word in self._dictionary:
			return self._dictionary[word].word_id
		dic_entry = WordDictionaryEntry(word, self.current_id)
		self.current_id += 1
		self._dictionary[dic_entry.word] = dic_entry
		return dic_entry.word_id

	def add_word(self, word):
		self.get_word_id(word)


class ForwardIndex:

	def __init__(self, word_dic, index_dir = "index"):
		self.index_dir = index_dir
		self._word_dic = word_dic
		self._forward_index_path = index_dir + "/forward_index"
		if not os.path.isfile(self._forward_index_path):
			with open(self._forward_index_path, mode = "w"):
				pass
		self._forward_index = open(self._forward_index_path, mode = "rb+")

	def load(self):
		pass

	def index(self, data):
		pass

	def get_entry(self, page_id):
		pass

	def close(self):
		self._forward_index.close()


class Indexer:
	"""
	A indexer that accepts page information from a web crawler and index it based on the idea presented in the paper
	The Anatomy of a Large-Scale Hypertextual Web Search Engine. Currently, it is not thread safe.
	"""

	def __init__(self, index_dir = "index"):
		self.index_dir = index_dir
		self._forward_index_path = index_dir + "/forward_index"
		self._reverse_index_path = index_dir + "/reverse_index"
		self._lexicon_path = index_dir + "/lexicon_index"
		self._dictionary_path = index_dir + "/dictionary"
		self._forward_index = open(self._forward_index_path, mode = "rb+")
		self._reverse_index = open(self._reverse_index_path, mode = "rb+")
		self._lexicon = open(self._lexicon_path, mode = "rb+")
		self._dictionary = WordDictionary(self._dictionary_path)

	def load(self):
		self._dictionary.load()

	def index(self, data):
		pass

	def search_by_keywords(self, keywords):
		return []

	def close(self):
		self._dictionary.close()

	def _convert_word_to_id(self, word):
		if word in self._dictionary:
			return self._dictionary[word]


class TestForwardIndex(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		os.mkdir("index")

	def test_index(self):
		word_dictionary = WordDictionary("word_dict")
		word_dictionary.load()
		anchors = [Anchor("Example", "https://www.example.com")]
		headers = ["Go to example"]
		texts = ["Go with example"]
		page = PageDocument(doc_id = 1, title = "Test Page", checksum = "12345", url = "https://www.test.com",
		                    anchors = anchors, texts = texts, headers = headers)
		forward_index = ForwardIndex(word_dictionary, "index")
		try:
			forward_index.load()
			forward_index.index(page)
			forward_entry = forward_index.get_entry(1)
			expected_entry = ForwardIndexEntry(1)
			expected_entry.hits[word_dictionary.get_word_id("Go")] = [Hit(1, 0, 0), Hit(4, 0, 0)]
			expected_entry.hits[word_dictionary.get_word_id("example")] = [Hit(2, 0, 0), Hit(1, 0, 2), Hit(4, 0, 2)]
			expected_entry.hits[word_dictionary.get_word_id("to")] = [Hit(4, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("with")] = [Hit(1, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("test")] = [Hit(3, 0, 0)]
			expected_entry.hits[word_dictionary.get_word_id("page")] = [Hit(3, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("https://www.test.com")] = [Hit(5, 0, 0)]
			self.assertEqual(expected_entry, forward_entry, "Failed to index/retrieve correctly")
			word_dictionary.close()
		finally:
			forward_index.close()

	@classmethod
	def tearDownClass(cls):
		shutil.rmtree("index")
		os.remove("word_dict")


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
		anchors2 = [Anchor("Page 1", "https://www.page1.com")]
		page2 = PageDocument(doc_id = 1, title = "Page 2", checksum = "67890", url = "https://www.page2.com",
		                     texts = texts2, anchors = anchors2, headers = headers2)

		headers3 = ["Page 3 test", "References"]
		texts3 = "This should be the third ranked by page rank", "Welcome to page 3", "Page two is great", "Page one is great"
		anchors3 = [Anchor("Page 2", "https://www.page2.com"), Anchor("Page 1", "https://www.page1.com")]
		page3 = PageDocument(doc_id = 2, title = "Page 3", checksum = "09876", url = "https://www.page3.com",
		                     texts = texts3, anchors = anchors3, headers = headers3)
		return page1, page2, page3

	def test_single_entry(self):
		indexer = self.load_indexer()
		anchors = Anchor("Example", "https://www.example.com"), Anchor("Facebook", "https://www.facebook.com")
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
		page = PageDocument(doc_id = 1, title = "Test persistence", checksum = "3782",
		                    url = "https://www.test-persistence.com")
		indexer.index(page)
		indexer.close()
		indexer = self.load_indexer()
		query_result = indexer.search_by_keywords("persistence")
		self.assertEqual(1, len(query_result), "Failed to persist")
		self.assertEqual(1, query_result[0], "Failed to maintain integrity")


class TestWordDictionary(unittest.TestCase):

	def test_word_to_id(self):
		dictionary = WordDictionary("dictionary")
		dictionary.load()
		lexicon_id = dictionary.get_word_id("lexicon")
		test_id = dictionary.get_word_id("test")
		url_id = dictionary.get_word_id("https://www.google.com")
		dictionary.close()
		self.assertEqual(1, lexicon_id, "Dictionary not providing id correctly")
		self.assertEqual(2, test_id, "Dictionary not incrementing id correctly")
		self.assertEqual(3, url_id, "Dictionary failed to handle url")

	def test_persistence(self):
		dictionary = WordDictionary("persistence_test")
		dictionary.load()
		dictionary.add_word("lexicon")
		dictionary.add_word("test")
		dictionary.add_word("https://www.google.com")
		dictionary.close()
		dictionary = WordDictionary("persistence_test")
		dictionary.load()
		self.assertEqual(2, dictionary.get_word_id("test"), "Dictionary failed to sync")
		self.assertEqual(1, dictionary.get_word_id("lexicon"), "Dictionary failed to sync")
		self.assertEqual(3, dictionary.get_word_id("https://www.google.com"), "Dictionary failed to sync")
		dictionary.close()

	@classmethod
	def tearDownClass(cls):
		os.remove("dictionary")
		os.remove("persistence_test")


class TestFileBinarySearch(unittest.TestCase):

	@staticmethod
	def alphebet_comparator(target, current):
		if target == current:
			return 0
		if target > current:
			return 1
		if target < current:
			return -1

	def test_regular_binary_search(self):
		with open("test_regular", mode = "wb") as file:
			file.write(b"abcdefg")
		with open("test_regular", mode = "rb") as file:
			is_found, target, position = file_binary_search(file, b'f', TestFileBinarySearch.alphebet_comparator, 1, 0,
			                                                7)
			self.assertTrue(is_found, "Binary search failed to find")
			self.assertEqual(b'f', target, "Binary search failed to return the correct target")
			self.assertEqual(5, position, "Binary search failed to find the correct position")

	def test_one_entry_binary_search(self):
		with open("test_one_entry", mode = "wb") as file:
			file.write(b"a")
		with open("test_one_entry", mode = "rb") as file:
			is_found, target, position = file_binary_search(file, b'a', TestFileBinarySearch.alphebet_comparator, 1, 0,
			                                                1)
			self.assertTrue(is_found, "Binary search failed to find")
			self.assertEqual(b'a', target, "Binary search failed to return the correct target")
			self.assertEqual(0, position, "Binary search failed to find the correct position")

	def test_not_found_binary_search(self):
		with open("test_not_found", mode = "wb") as file:
			file.write(b"abcdefgijk")
		with open("test_not_found", mode = "rb") as file:
			is_found, target, position = file_binary_search(file, b'h', TestFileBinarySearch.alphebet_comparator, 1, 0,
			                                                10)
			self.assertFalse(is_found, "Binary search false positive")
			self.assertEqual(None, target, "Binary search found the wrong entry")
			self.assertEqual(7, position, "Binary search failed to find the correct position")

	@classmethod
	def tearDownClass(cls):
		os.remove("test_regular")
		os.remove("test_one_entry")
		os.remove("test_not_found")
