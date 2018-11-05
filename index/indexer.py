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
	"""
	performs a recursive binary search on a file for a specific entry of bytes.
	:param file: the file to search.
	:param target: the target entry.
	:param comparator: the compare function that compares the target to bytes representing an entry.
	:param entry_size: the size of a single entry.
	:param start: the start position, inclusive.
	:param end: the end position, exclusive.
	:return: whether the entry was found, the bytes of the entry found if found, the position of the found entry
	or where it should be.
	"""

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
	"""
	merges dictionaries containing lists such that the result dictionary would have the keys and list entries of
	all the input dictionaries.
	:param dictionaries: a iterable series of dictionaries.
	:return: the result dictionary.
	"""

	result_dict = dict()
	for dictionary in dictionaries:
		for key, value in dictionary.items():
			if key not in result_dict:
				result_dict[key] = list()
			result_dict[key].extend(dictionary[key])
	return result_dict


def stripe_enclosing_punctuation(target: str):
	"""
	removes punctuations around a string.
	:param target: the string to filter.
	:return: a new string without the surrounding punctuations.
	"""

	if len(target) == 0:
		return target
	lower_bound, upper_bound = 0, len(target)
	if target[0] in string.punctuation:
		lower_bound += 1
	if target[-1] in string.punctuation:
		upper_bound -= 1
	return target[lower_bound:upper_bound]


class WordDictionary:
	"""
	A dictionary of words that maps a single word to a word_id. The mapping of words are persisted in a text file.
	"""

	def __init__(self, path):
		"""
		creates a new word dictionary specifying the path to the persistence text file.
		:param path: the path to the text file.
		"""

		self.path = path
		self._dictionary = dict()
		self.current_id = 0

	def load(self):
		"""
		loads this dictionary from the text file specified by the path.
		:return: None.
		"""

		if not os.path.isfile(self.path):
			with open(self.path, mode="w"):
				pass

		dictionary_file = open(self.path, mode="r")
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
		"""
		cleans up all resources and writes the entries to the text file.
		:return: None.
		"""

		dictionary_file = open(self.path, mode="w")
		try:
			for entry in self._dictionary.values():
				dictionary_file.write(entry.pack() + '\n')
		finally:
			dictionary_file.close()

	def get_word_id(self, word):
		"""
		gets the word id of a word. if the word doesn't exists in the dictionary, a new entry would be created with
		a newly assigned word id.
		:param word: the word to get id of.
		:return: the word if of the word.
		"""

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
	"""
	The forward index of the search engine. This maps a page to the words it contains. Each word has a hit list of
	Hit that describes the kind of hit and the location of the hit.
	"""

	def __init__(self, word_dic, index_dir="index"):
		"""
		creates a new forward entry with the index path and word dictionary.
		:param word_dic: the word dictionary to map words
		:param index_dir: the directory where the indexes would be stored.
		"""

		self.index_dir = index_dir
		self._word_dic = word_dic
		self._forward_index_path = index_dir + "/forward_index"
		self._forward_index_map_path = index_dir + "/forward_index_map"
		self._forward_index = open(self._forward_index_path, mode="ab+")
		self._index_size = os.path.getsize(self._forward_index_path)
		self._position_mapping = dict()

	def load(self):
		"""
		loads the index from the files.
		:return: None.
		"""

		self._position_mapping = load_dictionary(self._forward_index_map_path)

	def index(self, data):
		"""
		index a PageDocument to the forward index.
		:param data: the PageDocument to index.
		:return: the forward index entry representing the PageDocument.
		"""

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
		"""
		gets a ForwardIndexEntry by its page_id.
		:param page_id: the page id of the ForwardIndexEntry.
		:return: the ForwardIndexEntry or None if it doesn't exist.
		"""

		if page_id not in self._position_mapping:
			return None
		position = self._position_mapping[page_id]
		self._forward_index.seek(position, 0)
		return self._read_forward_entry(self._forward_index)

	def close(self):
		"""
		cleans up any resources and write any changes to file if necessary.
		:return: None.
		"""

		dump_dictionary(self._position_mapping, self._forward_index_map_path)
		self._forward_index.close()

	def _write_forward_entry(self, entry):
		"""
		writes a ForwardIndexEntry to the end of the forward index file.
		:param entry: the entry to write.
		:return: None.
		"""

		forward_binary = entry.pack()
		size = len(forward_binary)
		size_byte = struct.pack("!I", size)
		data = size_byte + forward_binary
		self._forward_index.write(data)
		self._position_mapping[entry.page_id] = self._index_size
		self._index_size += len(data)

	def _read_forward_entry(self, file):
		"""
		reads a ForwardIndexEntry from a file seeked to the beginning of the entry to read.
		:param file: the seeked file.
		:return: the read ForwardIndexEntry.
		"""

		metabytes = file.read(4)
		size = struct.unpack("!I", metabytes)
		data_bytes = file.read(size[0])
		return ForwardIndexEntry.unpack(data_bytes)

	def _title_to_hits(self, title):
		"""
		converts the title of the PageDocument to Title Hits.
		:param title: the title of the PageDocument.
		:return: A dictionary mapping the word ids in the title to the hit list of each word.
		"""

		return self._scan_hits([title], Hit.TITLE_HIT)

	def _headers_to_hits(self, headers):
		"""
		converts the headers of the PageDocument to Header Hits.
		:param headers: the headers of the PageDocument.
		:return: a dictionary mapping the word ids in the headers to their hit list.
		"""

		return self._scan_hits(headers, Hit.HEADER_HIT)

	def _texts_to_hits(self, texts):
		"""
		converts the text sections of the PageDocument to Text Hits.
		:param texts: the text sections of the PageDocument.
		:return: a dictionary mapping the word ids in the text sections to their hit list.
		"""

		return self._scan_hits(texts, Hit.TEXT_HIT)

	def _anchor_to_hits(self, anchors):
		"""
		converts the anchors of the PageDocument to Anchor Hits.
		:param anchors: the anchors of the PageDocument.
		:return: a dictionary mapping the word ids in the anchors to their hit list.
		"""

		anchor_texts = []
		for anchor in anchors:
			anchor_texts.append(anchor.text)
		return self._scan_hits(anchor_texts, Hit.ANCHOR_HIT)

	def _url_to_hits(self, url):
		"""
		converts the url of the page to URL Hit.
		:param url: the url of the page.
		:return: a dictionary with the word id of the url mapped to its Hit.
		"""

		return self._scan_hits([url], Hit.URL_HIT)

	def _scan_hits(self, sections, kind):
		"""
		converts sections of content to dictionary mapping word ids in the sections to hit list of the specified kind.
		:param sections: the iterable sections of strings to convert to hit lists.
		:param kind: the kind of Hit
		:return: a dictionary mapping word ids in the sections to hit lists.
		"""

		master_result = dict()
		for count, section in enumerate(sections):
			result_dict = self._scan_section(count, section, kind)
			master_result = merge_list_dictionaries((master_result, result_dict))
		return master_result

	def _scan_section(self, section_num, section: str, kind: int):
		"""
		converts an individual section to a dictionary mapping the word ids in the section to their hit list.
		:param section_num: the section number of the section.
		:param section: the string section itself.
		:param kind: the kind of Hit of this section.
		:return: a dictionary mapping the word ids in the section to their hit list.
		"""

		words = section.split(" ")
		result = dict()
		for count, word in enumerate(words):
			word_id = self._word_dic.get_word_id(word)
			if word_id not in result:
				result[word_id] = []
			result[word_id].append(Hit(kind, section_num, count))
		return result


class ReverseIndex:
	"""
	A reverse index that maps a word to documents. Each document contains a hit list that are hits of the mapping word.
	"""

	def __init__(self, index_dir="index"):
		"""
		creates a new ReverseIndex at the specified index directory.
		:param index_dir: the directory that the ReverseIndex will reside in.
		"""

		self.index_dir = index_dir
		self._reverse_index_path = index_dir + "/reverse_indexes"
		self._lexicon_path = index_dir + "/lexicon"
		self._lexicon = dict()

	def load(self):
		"""
		loads the ReverseIndex from the directory.
		:return: None.
		"""

		if not os.path.isdir(self._reverse_index_path):
			os.mkdir(self._reverse_index_path)
		self._load_lexicon()

	def index(self, forward_entry):
		"""
		converts a ForwardIndexEntry to several ReverseIndexEntry and then index them.
		:param forward_entry: the forward entry to index.
		:return: all the reverse entries that came from the forward entry in the form of a dictionary with
		word id -> ReverseIndexEntry.
		"""

		reverse_entries = self._convert_to_reverse_indexes(forward_entry)
		for word_id, entries in reverse_entries.items():
			file_id = self._reverse_index_path + "/" + str(word_id)
			with open(file_id, "ab+") as reverse_index_file:
				for e in entries:
					reverse_index_file.write(e.pack())
		self._add_to_lexicon(reverse_entries)
		return reverse_entries

	def get_entries(self, word_id):
		"""
		gets all reverse entries that are mapped by the specified word.
		:param word_id: the word id to search for.
		:return: ReverseIndexEntry mapped by this word id.
		"""

		entries = self._load_reverse_entries(word_id)
		for entry in entries:
			entry.word_id = word_id
		return entries

	def get_page_ids(self, word_id):
		"""
		gets the page id of all pages containing the word referenced by this word id.
		:param word_id: the word id to search for.
		:return: all page ids referenced by this word id.
		"""

		return self._lexicon.get(word_id, [])

	def close(self):
		"""
		clean up all resources and write any changes to file.
		:return: None.
		"""

		self._write_lexicon()

	def _convert_to_reverse_indexes(self, forward_entry):
		"""
		converts a ForwardIndexEntry to a mapping of word id to ReverseIndexEntry.
		:param forward_entry: the forward entry to convert.
		:return: a mapping of word id -> ReverseIndexEntry.
		"""

		result = dict()
		for word_id, hit_list in forward_entry.hits.items():
			if word_id not in result:
				result[word_id] = []
			entry = ReverseIndexEntry(word_id, forward_entry.page_id)
			entry.hits.extend(hit_list)
			result[word_id].append(entry)
		return result

	def _add_to_lexicon(self, reverse_entries):
		"""
		adds a mapping of reverse entries to the Lexicon according to the word id.
		:param reverse_entries: the reverse entries mapping to add
		:return: None.
		"""

		for word_id, entries in reverse_entries.items():
			for e in entries:
				self._insert_to_lexicon(word_id, e.page_id)

	def _insert_to_lexicon(self, word_id, page_id):
		"""
		inserts a page to the lexicon.
		:param word_id: the word that the page contains.
		:param page_id: the id of the page.
		:return: None.
		"""

		if word_id not in self._lexicon:
			self._lexicon[word_id] = SortedList()
		self._lexicon[word_id].add(page_id)

	def _load_lexicon(self):
		"""
		loads all entries from the lexicon file.
		:return: None.
		"""

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
		"""
		writes all of the the Lexicon in memory to file.
		:return: None.
		"""

		with open(self._lexicon_path, "ab") as lexicon_file:
			for word_id, pages in self._lexicon.items():
				entry = LexiconEntry(word_id)
				entry.pages.extend(pages)
				lexicon_file.write(entry.pack())

	def _load_reverse_entries(self, word_id):
		"""
		load all reverse entries mapped by the specified word.
		:param word_id: the id of the word.
		:return: a list of ReverseIndexEntry.
		"""

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

	def __init__(self, index_dir="index", dampener=0.8):
		"""
		creates a new Indexer specifying index directory and weight dampener.
		:param index_dir: the directory of the indexes.
		:param dampener: the dampening factor.
		"""

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
		"""
		load the index.
		:return: None.
		"""

		self._word_dictionary.load()
		self._forward_index.load()
		self._reverse_index.load()
		self._link_out_counts = load_dictionary(self._link_out_path)
		self._references_tracker = load_dictionary(self._references_tracker_path)
		self._url_page_id_mapper = load_dictionary(self._url_mapper_path)
		self._page_id_url_mapper = load_dictionary(self._page_id_mapper_path)

	def index(self, data):
		"""
		indexes a PageDocument to the index.
		:param data: the PageDocument to index.
		:return: None.
		"""

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
		"""
		search the index by keywords.
		:param keywords: the keywords to search for.
		:return: the result sorted by pagerank and keywords.
		"""

		keyword_id = self._word_dictionary.get_word_id(keywords)
		pages = self._reverse_index.get_page_ids(keyword_id)
		ranked_pages = {page_id: self._page_rank(page_id) for page_id in pages}
		sorted_pages = []
		for key, item in sorted(ranked_pages.items(), key=lambda entry: entry[1], reverse=True):
			sorted_pages.append(key)
		return sorted_pages

	def close(self):
		"""
		cleans up resources and write changes to file.
		:return: None.
		"""

		self._word_dictionary.close()
		self._forward_index.close()
		self._reverse_index.close()
		dump_dictionary(self._link_out_counts, self._link_out_path)
		dump_dictionary(self._references_tracker, self._references_tracker_path)
		dump_dictionary(self._url_page_id_mapper, self._url_mapper_path)

	def _page_rank(self, page_id):
		"""
		calculates the page rank of a page id recursively.
		:param page_id: the page id of the page to calculate pagerank for.
		:return: the page rank value.
		"""

		return self._page_rank_recursive(page_id, dict())

	def _page_rank_recursive(self, page_id, tracker):
		"""
		the recursive function that calculates page rank.
		:param page_id: the page id to calculate pagerank for.
		:param tracker: a dictionary that tracks existing page ranks so that the recursion stops eventually.
		:return: the calculated page rank of the given page id.
		"""

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
		page = PageDocument(doc_id=1, title="Test Page", checksum="12345", url="https://www.test.com",
		                    anchors=anchors, texts=texts, headers=headers)
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
		page1 = PageDocument(doc_id=3, title="Page 1", checksum="12345", url="https://www.page1.com",
		                     texts=texts1, headers=headers1)

		headers2 = ["Page 2 test", "References"]
		texts2 = "This should be the second ranked by page rank", "Welcome to page 2", "Page one is great"
		anchors2 = [Anchor("Page 1", "https://www.page1.com")]
		page2 = PageDocument(doc_id=1, title="Page 2", checksum="67890", url="https://www.page2.com",
		                     texts=texts2, anchors=anchors2, headers=headers2)

		headers3 = ["Page 3 test", "References"]
		texts3 = "This should be the third ranked by page rank", "Welcome to page 3", "Page two is great", "Page one is great"
		anchors3 = [Anchor("Page 2", "https://www.page2.com"), Anchor("Page 1", "https://www.page1.com")]
		page3 = PageDocument(doc_id=2, title="Page 3", checksum="09876", url="https://www.page3.com",
		                     texts=texts3, anchors=anchors3, headers=headers3)
		return page1, page2, page3

	def test_single_entry(self):
		indexer = self.load_indexer()
		anchors = Anchor("Example", "https://www.example.com"), Anchor("Facebook", "https://www.facebook.com")
		headers = "Go to example", "Like on facebook"
		texts = "This is a page used to test the indexer", "If you like this page, like on Facebook"
		page = PageDocument(doc_id=1, title="Test Page", checksum="12345", url="https://www.test.com",
		                    anchors=anchors, texts=texts, headers=headers)
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
		page = PageDocument(doc_id=1, title="Test persistence", checksum="3782",
		                    url="https://www.test-persistence.com")
		indexer.index(page)
		indexer.close()
		indexer = self.load_indexer()
		query_result = indexer.search_by_keywords("persistence")
		self.assertEqual(1, len(query_result), "Failed to persist")
		self.assertEqual(1, query_result[0], "Failed to maintain integrity")
		indexer.close()

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
		with open("test_regular", mode="wb") as file:
			file.write(b"abcdefg")
		with open("test_regular", mode="rb") as file:
			is_found, target, position = file_binary_search(file, b'f', TestFileBinarySearch.alphebet_comparator, 1, 0,
			                                                7)
			self.assertTrue(is_found, "Binary search failed to find")
			self.assertEqual(b'f', target, "Binary search failed to return the correct target")
			self.assertEqual(5, position, "Binary search failed to find the correct position")

	def test_one_entry_binary_search(self):
		with open("test_one_entry", mode="wb") as file:
			file.write(b"a")
		with open("test_one_entry", mode="rb") as file:
			is_found, target, position = file_binary_search(file, b'a', TestFileBinarySearch.alphebet_comparator, 1, 0,
			                                                1)
			self.assertTrue(is_found, "Binary search failed to find")
			self.assertEqual(b'a', target, "Binary search failed to return the correct target")
			self.assertEqual(0, position, "Binary search failed to find the correct position")

	def test_not_found_binary_search(self):
		with open("test_not_found", mode="wb") as file:
			file.write(b"abcdefgijk")
		with open("test_not_found", mode="rb") as file:
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
