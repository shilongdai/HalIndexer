import os
import shutil
import string
import struct
import unittest

from sortedcontainers import SortedList

from data.web import Anchor
from data.web import PageDocument
from index.entry import ForwardIndexEntry
from index.entry import Hit
from index.entry import LexiconEntry
from index.entry import ReverseIndexEntry
from index.entry import WordDictionaryEntry
from index.entry import dump_dictionary
from index.entry import load_dictionary


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


def merge_list_dictionaries(dictionaries):
	result_dict = dict()
	for dictionary in dictionaries:
		for key, value in dictionary.items():
			if key not in result_dict:
				result_dict[key] = list()
			result_dict[key].extend(dictionary[key])
	return result_dict


def stripe_enclosing_punctuation(target: str):
	if len(target) == 0:
		return target
	lower_bound, upper_bound = 0, len(target)
	if target[0] in string.punctuation:
		lower_bound += 1
	if target[-1] in string.punctuation:
		upper_bound -= 1
	return target[lower_bound:upper_bound]


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
		word = stripe_enclosing_punctuation(word.rstrip())
		word = word.lower()
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
		self._forward_index_map_path = index_dir + "/forward_index_map"
		self._forward_index = open(self._forward_index_path, mode = "ab+")
		self._index_size = os.path.getsize(self._forward_index_path)
		self._position_mapping = dict()

	def load(self):
		self._position_mapping = load_dictionary(self._forward_index_map_path)

	def index(self, data):
		forward_entry = ForwardIndexEntry(data.doc_id)
		title_hits = self._title_to_hits(data.title)
		header_hits = self._headers_to_hits(data.headers)
		text_hits = self._texts_to_hits(data.texts)
		anchor_hits = self._anchor_to_hits(data.anchors)
		url_hits = self._url_to_hits(data.url)
		master_dic = merge_list_dictionaries((title_hits, header_hits, text_hits, anchor_hits, url_hits))
		forward_entry.hits = master_dic
		self._write_forward_entry(forward_entry)
		return forward_entry

	def get_entry(self, page_id):
		if page_id not in self._position_mapping:
			return None
		position = self._position_mapping[page_id]
		self._forward_index.seek(position, 0)
		return self._read_forward_entry(self._forward_index)

	def close(self):
		dump_dictionary(self._position_mapping, self._forward_index_map_path)
		self._forward_index.close()

	def _write_forward_entry(self, entry):
		forward_binary = entry.pack()
		size = len(forward_binary)
		size_byte = struct.pack("!I", size)
		data = size_byte + forward_binary
		self._forward_index.write(data)
		self._position_mapping[entry.page_id] = self._index_size
		self._index_size += len(data)

	def _read_forward_entry(self, file):
		metabytes = file.read(4)
		size = struct.unpack("!I", metabytes)
		data_bytes = file.read(size[0])
		return ForwardIndexEntry.unpack(data_bytes)

	def _title_to_hits(self, title):
		return self._scan_hits([title], Hit.TITLE_HIT)

	def _headers_to_hits(self, headers):
		return self._scan_hits(headers, Hit.HEADER_HIT)

	def _texts_to_hits(self, texts):
		return self._scan_hits(texts, Hit.TEXT_HIT)

	def _anchor_to_hits(self, anchors):
		anchor_texts = []
		for anchor in anchors:
			anchor_texts.append(anchor.text)
		return self._scan_hits(anchor_texts, Hit.ANCHOR_HIT)

	def _url_to_hits(self, url):
		return self._scan_hits([url], Hit.URL_HIT)

	def _scan_hits(self, sections, kind):
		master_result = dict()
		for count, section in enumerate(sections):
			result_dict = self._scan_section(count, section, kind)
			master_result = merge_list_dictionaries((master_result, result_dict))
		return master_result

	def _scan_section(self, section_num, section: str, kind: int):
		words = section.split(" ")
		result = dict()
		for count, word in enumerate(words):
			word_id = self._word_dic.get_word_id(word)
			if word_id not in result:
				result[word_id] = []
			result[word_id].append(Hit(kind, section_num, count))
		return result


class ReverseIndex:

	def __init__(self, index_dir = "index"):
		self.index_dir = index_dir
		self._reverse_index_path = index_dir + "/reverse_indexes"
		self._lexicon_path = index_dir + "/lexicon"
		self._lexicon = dict()

	def load(self):
		if not os.path.isdir(self._reverse_index_path):
			os.mkdir(self._reverse_index_path)
		self._load_lexicon()

	def index(self, forward_entry):
		reverse_entries = self._convert_to_reverse_indexes(forward_entry)
		for word_id, entries in reverse_entries.items():
			file_id = self._reverse_index_path + "/" + str(word_id)
			with open(file_id, "ab+") as reverse_index_file:
				for e in entries:
					reverse_index_file.write(e.pack())
		self._add_to_lexicon(reverse_entries)
		return reverse_entries

	def get_entries(self, word_id):
		entries = self._load_reverse_entries(word_id)
		for entry in entries:
			entry.word_id = word_id
		return entries

	def get_page_ids(self, word_id):
		return self._lexicon.get(word_id, [])

	def close(self):
		self._write_lexicon()

	def _convert_to_reverse_indexes(self, forward_entry):
		result = dict()
		for word_id, hit_list in forward_entry.hits.items():
			if word_id not in result:
				result[word_id] = []
			entry = ReverseIndexEntry(word_id, forward_entry.page_id)
			entry.hits.extend(hit_list)
			result[word_id].append(entry)
		return result

	def _add_to_lexicon(self, reverse_entries):
		for word_id, entries in reverse_entries.items():
			for e in entries:
				self._insert_to_lexicon(word_id, e.page_id)

	def _insert_to_lexicon(self, word_id, page_id):
		if word_id not in self._lexicon:
			self._lexicon[word_id] = SortedList()
		self._lexicon[word_id].add(page_id)

	def _load_lexicon(self):
		if not os.path.isfile(self._lexicon_path):
			with open(self._lexicon_path, "w"):
				pass
		with open(self._lexicon_path, "rb") as lexicon_file:
			lexicon_data = lexicon_file.read()
			start = 0
			end = len(lexicon_data)
			while start < end:
				entry_len = struct.unpack("!I", lexicon_data[start: start + 4])
				entry = LexiconEntry.unpack(lexicon_data[start:start + entry_len[0] + 4])
				start += entry_len[0]
				start += 4
				for page in entry.pages:
					self._insert_to_lexicon(entry.word_id, page)

	def _write_lexicon(self):
		with open(self._lexicon_path, "ab") as lexicon_file:
			for word_id, pages in self._lexicon.items():
				entry = LexiconEntry(word_id)
				entry.pages.extend(pages)
				lexicon_file.write(entry.pack())

	def _load_reverse_entries(self, word_id):
		path_to_entries = self._reverse_index_path + "/" + str(word_id)
		if not os.path.isfile(path_to_entries):
			with open(path_to_entries, "w"):
				pass
		result = []
		with open(path_to_entries, "rb") as reverse_file:
			data = reverse_file.read()
			start = 0
			end = len(data)
			while start < end:
				entry_len = struct.unpack("!I", data[start: start + 4])
				entry = ReverseIndexEntry.unpack(data[start:start + entry_len[0] + 4])
				start += entry_len[0]
				start += 4
				result.append(entry)
		return result


class Indexer:
	"""
	A indexer that accepts page information from a web crawler and index it based on the idea presented in the paper
	The Anatomy of a Large-Scale Hypertextual Web Search Engine. Currently, it is not thread safe.
	"""

	def __init__(self, index_dir = "index", dampener = 0.8):
		if not os.path.isdir(index_dir):
			os.mkdir(index_dir)
		self.index_dir = index_dir
		self._dampener = dampener
		self._word_dictionary_path = index_dir + "/word_dict"
		self._link_out_path = index_dir + "/link_out"
		self._references_tracker_path = index_dir + "/reference_count"
		self._url_mapper_path = index_dir + "/url_mapper"
		self._page_id_mapper_path = index_dir + "/page_id_mapper"
		self._word_dictionary = WordDictionary(self._word_dictionary_path)
		self._forward_index = ForwardIndex(self._word_dictionary, index_dir)
		self._reverse_index = ReverseIndex(index_dir)
		self._link_out_counts = dict()
		self._references_tracker = dict()
		self._url_page_id_mapper = dict()
		self._page_id_url_mapper = dict()

	def load(self):
		self._word_dictionary.load()
		self._forward_index.load()
		self._reverse_index.load()
		self._link_out_counts = load_dictionary(self._link_out_path)
		self._references_tracker = load_dictionary(self._references_tracker_path)
		self._url_page_id_mapper = load_dictionary(self._url_mapper_path)
		self._page_id_url_mapper = load_dictionary(self._page_id_mapper_path)

	def index(self, data):
		if data.url in self._url_page_id_mapper:
			return
		forward_entry = self._forward_index.index(data)
		self._reverse_index.index(forward_entry)
		self._url_page_id_mapper[data.url] = forward_entry.page_id
		self._page_id_url_mapper[forward_entry.page_id] = data.url
		self._link_out_counts[forward_entry.page_id] = len(data.anchors)
		unique_anchors = set(data.anchors)
		for anchor in unique_anchors:
			if anchor.url not in self._references_tracker:
				self._references_tracker[anchor.url] = []
			self._references_tracker[anchor.url].append(forward_entry.page_id)

	def search_by_keywords(self, keywords):
		keyword_id = self._word_dictionary.get_word_id(keywords)
		pages = self._reverse_index.get_page_ids(keyword_id)
		ranked_pages = {page_id: self._page_rank(page_id) for page_id in pages}
		sorted_pages = []
		for key, item in sorted(ranked_pages.items(), key = lambda entry: entry[1], reverse = True):
			sorted_pages.append(key)
		return sorted_pages

	def close(self):
		self._word_dictionary.close()
		self._forward_index.close()
		self._reverse_index.close()
		dump_dictionary(self._link_out_counts, self._link_out_path)
		dump_dictionary(self._references_tracker, self._references_tracker_path)
		dump_dictionary(self._url_page_id_mapper, self._url_mapper_path)

	def _page_rank(self, page_id):
		return self._page_rank_recursive(page_id, dict())

	def _page_rank_recursive(self, page_id, tracker):
		if page_id in tracker:
			return tracker[page_id]
		rand_probability = 1 - self._dampener
		link_probability = 0
		if page_id not in self._page_id_url_mapper:
			return rand_probability
		url = self._page_id_url_mapper[page_id]
		for page in self._references_tracker.get(url, []):
			link_probability = link_probability + (
					self._page_rank_recursive(page, tracker) / self._link_out_counts[page])
		page_rank = rand_probability + link_probability
		tracker[page_id] = page_rank
		return page_rank


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
			expected_entry.hits[word_dictionary.get_word_id("test")] = [Hit(Hit.TITLE_HIT, 0, 0)]
			expected_entry.hits[word_dictionary.get_word_id("page")] = [Hit(Hit.TITLE_HIT, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("Go")] = [Hit(Hit.HEADER_HIT, 0, 0),
			                                                          Hit(Hit.TEXT_HIT, 0, 0)]
			expected_entry.hits[word_dictionary.get_word_id("to")] = [Hit(Hit.HEADER_HIT, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("example")] = [Hit(Hit.HEADER_HIT, 0, 2),
			                                                               Hit(Hit.TEXT_HIT, 0, 2),
			                                                               Hit(Hit.ANCHOR_HIT, 0, 0)]
			expected_entry.hits[word_dictionary.get_word_id("with")] = [Hit(Hit.TEXT_HIT, 0, 1)]
			expected_entry.hits[word_dictionary.get_word_id("https://www.test.com")] = [Hit(Hit.URL_HIT, 0, 0)]
			self.assertEqual(expected_entry, forward_entry, "Failed to index/retrieve correctly")
		finally:
			forward_index.close()
			word_dictionary.close()

	@classmethod
	def tearDownClass(cls):
		shutil.rmtree("index")
		os.remove("word_dict")


class TestReverseIndex(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		os.mkdir("index")

	def test_index(self):
		word_dictionary = WordDictionary("word_dict")
		word_dictionary.load()
		forward_entry = ForwardIndexEntry(1)
		forward_entry.hits[word_dictionary.get_word_id("Go")] = [Hit(Hit.HEADER_HIT, 0, 0),
		                                                         Hit(Hit.TEXT_HIT, 0, 0)]
		forward_entry.hits[word_dictionary.get_word_id("example")] = [Hit(Hit.HEADER_HIT, 0, 2),
		                                                              Hit(Hit.TEXT_HIT, 0, 2),
		                                                              Hit(Hit.ANCHOR_HIT, 0, 0)]
		reverse_index = ReverseIndex()
		try:
			reverse_index.load()
			reverse_index.index(forward_entry)
			reverse_entries_go = reverse_index.get_entries(word_dictionary.get_word_id("go"))
			reverse_entries_example = reverse_index.get_entries(word_dictionary.get_word_id("example"))
			expected_entry_go = ReverseIndexEntry(word_dictionary.get_word_id("go"), 1)
			expected_entry_go.hits.extend([Hit(Hit.HEADER_HIT, 0, 0), Hit(Hit.TEXT_HIT, 0, 0)])
			expected_entry_example = ReverseIndexEntry(word_dictionary.get_word_id("example"), 1)
			expected_entry_example.hits.extend([Hit(Hit.HEADER_HIT, 0, 2),
			                                    Hit(Hit.TEXT_HIT, 0, 2),
			                                    Hit(Hit.ANCHOR_HIT, 0, 0)])
			self.assertEqual(1, len(reverse_entries_go))
			self.assertEqual(1, len(reverse_entries_example))
			self.assertEqual(expected_entry_go, reverse_entries_go[0])
			self.assertEqual(expected_entry_example, reverse_entries_example[0])
		finally:
			reverse_index.close()
			word_dictionary.close()

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
		for page in pages:
			indexer.index(page)
		query_result = indexer.search_by_keywords("Page")
		self.assertEqual(3, len(query_result), "search_by_keywords did not return the pages that it should match")
		self.assertEqual(3, query_result[0], "The page Page 1 should be ranked first")
		self.assertEqual(1, query_result[1], "The page Page 2 should be ranked second")
		self.assertEqual(2, query_result[2], "The page Page 3 should be ranked third")
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

	def tearDown(self):
		shutil.rmtree("index")


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

	def test_word_identification(self):
		dictionary = WordDictionary("identification_test")
		dictionary.load()
		dictionary.add_word("lexicon")
		self.assertEqual(1, dictionary.get_word_id("lexicon"), "Dictionary failed basic retrieval")
		self.assertEqual(1, dictionary.get_word_id("Lexicon"), "Dictionary failed capitalization identification")
		self.assertEqual(1, dictionary.get_word_id("LEXICON"), "Dictionary failed capitalization identification")
		self.assertEqual(1, dictionary.get_word_id("'lexicon'"), "Dictionary failed punctuation identification")
		self.assertEqual(1, dictionary.get_word_id("lexicon,"), "Dictionary failed punctuation identification")
		self.assertEqual(1, dictionary.get_word_id(".lexicon"), "Dictionary failed punctuation identification")

	@classmethod
	def tearDownClass(cls):
		os.remove("dictionary")
		os.remove("persistence_test")
		os.remove("identification_test")


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
