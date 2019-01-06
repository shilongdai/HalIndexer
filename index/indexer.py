import string
import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from index.entry import Anchor
from index.entry import Base
from index.entry import ForwardIndexEntry
from index.entry import ForwardMapper
from index.entry import Header
from index.entry import Hit
from index.entry import LexiconMapper
from index.entry import PageDocument
from index.entry import PageHitMapper
from index.entry import PageLinks
from index.entry import PageRankTracker
from index.entry import PageUrlMapper
from index.entry import ReferenceTracker
from index.entry import ReverseIndexEntry
from index.entry import TextSection
from index.entry import WordDictionaryEntry
from index.entry import WordHitMapper
from index.exceptions import ForwardMappingPersistException
from index.exceptions import HitListPersistException
from index.exceptions import IndexException
from index.exceptions import LexiconMappingPersistException
from index.exceptions import PageHitMappingPersistException
from index.exceptions import PageRankPersistException

Session = sessionmaker()
engine = None


def configure(connection_string, **kwargs):
	global engine
	global Session
	engine = create_engine(connection_string, **kwargs)
	Session.configure(bind = engine)


def cleanup():
	global Session
	if Session is not None:
		Session.close_all()
	if engine is not None:
		engine.dispose()
	Session = sessionmaker()


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
	removes punctuations around a string. If the string is all punctuation, then do nothing.
	:param target: the string to filter.
	:return: a new string without the surrounding punctuations. Or, if the string is all punctuation, the original string.
	"""

	if len(target) == 0:
		return target
	lower_bound, upper_bound = 0, len(target)
	acceptable_characters = string.ascii_letters + string.digits
	# check from beginning
	index = 0
	while index < len(target):
		if target[index] not in acceptable_characters:
			lower_bound += 1
			index += 1
		else:
			break
	# check from end
	index = len(target) - 1
	while index >= 0:
		if target[index] not in acceptable_characters:
			upper_bound -= 1
			index -= 1
		else:
			break
	if upper_bound <= lower_bound:
		return target
	return target[lower_bound:upper_bound]


class WordDictionary:
	"""
	A dictionary of words that maps a single word to a word_id. The mapping of words are persisted in a text file.
	"""

	def __init__(self):
		self._session = Session()

	def close(self):
		"""
		cleans up all resources.
		:return: None.
		"""
		self._session.close()

	def get_word_id(self, word):
		"""
		gets the word id of a word. if the word doesn't exists in the dictionary, a new entry would be created with
		a newly assigned word id.
		:param word: the word to get id of.
		:return: the word if of the word.
		"""

		word = stripe_enclosing_punctuation(word.rstrip())
		word = word.lower()
		query = self._session.query(WordDictionaryEntry).filter(WordDictionaryEntry.word == word)
		word_entry = query.one_or_none()
		if word_entry is not None:
			return word_entry.word_id
		else:
			return self.add_word(word)

	def add_word(self, word):
		word_entry = WordDictionaryEntry(word)
		self._session.add(word_entry)
		self._session.commit()
		return word_entry.word_id


class ForwardIndex:
	"""
	The forward index of the search engine. This maps a page to the words it contains. Each word has a hit list of
	Hit that describes the kind of hit and the location of the hit.
	"""

	def __init__(self, word_dic):
		"""
		creates a new forward entry with word dictionary.
		:param word_dic: the word dictionary to map words
		"""
		self._word_dic = word_dic
		self._session = Session()

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
		result = self._read_forward_entry(page_id)
		if len(result.hits) == 0:
			return None
		return result

	def close(self):
		"""
		cleans up any resources and write any changes to file if necessary.
		:return: None.
		"""
		self._session.close()

	def _write_forward_entry(self, entry):
		"""
		writes a ForwardIndexEntry to the database.
		:param entry: the entry to write.
		:return: None.
		"""
		for word_id, hit_list in entry.hits.items():
			try:
				self._write_hits(hit_list)
			except SQLAlchemyError as e:
				self._session.rollback()
				raise HitListPersistException(entry.page_id) from e
			forward_mapper = ForwardMapper(entry.page_id, word_id)
			try:
				for hit in hit_list:
					word_hit_mapper = WordHitMapper(word_id, hit.id)
					self._session.add(word_hit_mapper)
				self._session.add(forward_mapper)
				self._session.commit()
			except SQLAlchemyError as e:
				self._session.rollback()
				raise ForwardMappingPersistException(entry.page_id) from e

	def _write_hits(self, hits):
		self._session.add_all(hits)
		self._session.flush()

	def _read_forward_entry(self, page_id):
		"""
		reads a ForwardIndexEntry identified by a page id.
		:param page_id: the page id of the entry
		:return: the read ForwardIndexEntry.
		"""
		word_ids = self._session.query(ForwardMapper.word_id).filter(ForwardMapper.page_id == page_id).all()
		hit_dict = {}
		for word_id in word_ids:
			hit_ids = self._session.query(WordHitMapper.hit_id).filter(WordHitMapper.word_id == word_id[0]).all()
			hit_ids = [hit_id_tuple[0] for hit_id_tuple in hit_ids]
			hits = self._session.query(Hit).filter(Hit.id.in_(hit_ids)).all()
			hit_dict[word_id[0]] = hits
		result = ForwardIndexEntry(page_id)
		result.hits = hit_dict
		return result

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

		header_list = []
		for header in headers:
			header_list.append(header.text)
		return self._scan_hits(header_list, Hit.HEADER_HIT)

	def _texts_to_hits(self, texts):
		"""
		converts the text sections of the PageDocument to Text Hits.
		:param texts: the text sections of the PageDocument.
		:return: a dictionary mapping the word ids in the text sections to their hit list.
		"""

		text_list = []
		for text in texts:
			text_list.append(text.text)
		return self._scan_hits(text_list, Hit.TEXT_HIT)

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

	def __init__(self):
		"""
		creates a new ReverseIndex.
		"""
		self._session = Session()

	def index(self, forward_entry):
		"""
		converts a ForwardIndexEntry to several ReverseIndexEntry and then index them.
		:param forward_entry: the forward entry to index.
		:return: all the reverse entries that came from the forward entry in the form of a dictionary with
		word id -> ReverseIndexEntry.
		"""
		for word_id, hit_list in forward_entry.hits.items():
			try:
				page_hit_mappers = self._write_hit_list_mapping(forward_entry.page_id, hit_list)
			except SQLAlchemyError as e:
				self._session.rollback()
				raise PageHitMappingPersistException(word_id) from e
			try:
				for page_hit in page_hit_mappers:
					lexicon_mapper = LexiconMapper(word_id, page_hit.id)
					self._session.add(lexicon_mapper)
				self._session.commit()
			except SQLAlchemyError as e:
				self._session.rollback()
				raise LexiconMappingPersistException(word_id) from e

	def get_entry(self, word_id):
		"""
		gets all reverse entries that are mapped by the specified word.
		:param word_id: the word id to search for.
		:return: ReverseIndexEntry mapped by this word id.
		"""
		entry_ids = [result[0] for result in
		             self._session.query(LexiconMapper.page_hit_mapper_id).filter(LexiconMapper.word_id == word_id)]
		page_hit_mappers = self._session.query(PageHitMapper).filter(PageHitMapper.id.in_(entry_ids)).all()
		page_dict = {}
		for page_hit_mapper in page_hit_mappers:
			if page_hit_mapper.page_id not in page_dict:
				page_dict[page_hit_mapper.page_id] = []
			hit = self._session.query(Hit).filter(Hit.id == page_hit_mapper.hit_id).one_or_none()
			if hit is not None:
				page_dict[page_hit_mapper.page_id].append(hit)
		result = ReverseIndexEntry(word_id)
		result.pages = page_dict
		return result

	def get_page_ids(self, word_id):
		"""
		gets the page id of all pages containing the word referenced by this word id.
		:param word_id: the word id to search for.
		:return: all page ids referenced by this word id.
		"""
		reverse_entry = self.get_entry(word_id)
		return reverse_entry.pages.keys()

	def close(self):
		"""
		clean up all resources and write any changes to file.
		:return: None.
		"""
		self._session.close()

	def _write_hit_list_mapping(self, page_id, hit_list):
		to_save = []
		for hit in hit_list:
			to_save.append(PageHitMapper(page_id, hit.id))
		self._session.add_all(to_save)
		self._session.flush()
		return to_save


class SearchResult:

	def __init__(self, page_id, page_rank):
		self.page_id = page_id
		self.page_rank = page_rank

	def __eq__(self, o: "SearchResult") -> bool:
		try:
			if self.page_rank != o.page_rank:
				return False
			if self.page_id != o.page_id:
				return False
			return True
		except AttributeError:
			return False

	def __ne__(self, o: "SearchResult") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)


class Indexer:
	"""
	A indexer that accepts page information from a web crawler and index it based on the idea presented in the paper
	The Anatomy of a Large-Scale Hypertextual Web Search Engine. Currently, it is not thread safe.
	"""

	def __init__(self, dampener = 0.8, page_rank_iteration = 100):
		"""
		creates a new Indexer specifying index directory and weight dampener.
		:param dampener: the dampening factor.
		:param page_rank_iteration the amount of iteration to calculate page_rank
		"""
		self._dampener = dampener
		self._page_rank_iteration = page_rank_iteration
		self._session = Session()
		self._word_dictionary = WordDictionary()
		self._forward_index = ForwardIndex(self._word_dictionary)
		self._reverse_index = ReverseIndex()

	def index(self, data):
		"""
		indexes a PageDocument to the index.
		:param data: the PageDocument to index.
		:return: None.
		"""

		existing = self._session.query(PageUrlMapper).filter(PageUrlMapper.url == data.url).one_or_none()
		if existing is not None:
			return
		forward_entry = self._forward_index.index(data)
		self._reverse_index.index(forward_entry)
		url_page_id_mapper = PageUrlMapper(forward_entry.page_id, data.url)
		page_link_count = PageLinks(forward_entry.page_id, len(data.anchors))
		default_page_rank = PageRankTracker(data.url, 1 - self._dampener)
		reference_trackers = []
		unique_anchors = set(data.anchors)
		for anchor in unique_anchors:
			reference_trackers.append(ReferenceTracker(forward_entry.page_id, anchor.url))
		try:
			self._session.add(url_page_id_mapper)
			self._session.add(page_link_count)
			self._session.add_all(reference_trackers)
			self._session.add(default_page_rank)
			self._session.commit()
		except SQLAlchemyError as e:
			raise IndexException(data.url) from e

	def search_by_keywords(self, keywords):
		"""
		search the index by keywords.
		:param keywords: the keywords to search for.
		:return: the result sorted by pagerank and keywords.
		"""

		self._calculate_page_rank()
		keyword_id = self._word_dictionary.get_word_id(keywords)
		pages = self._reverse_index.get_page_ids(keyword_id)
		ranked_pages = {}
		for page_id in pages:
			url = self._session.query(PageUrlMapper.url).filter(PageUrlMapper.id == page_id).one()[0]
			page_rank = self._session.query(PageRankTracker.page_rank).filter(PageRankTracker.url == url).one()[0]
			ranked_pages[page_id] = page_rank
		sorted_pages = []
		for key, item in sorted(ranked_pages.items(), key = lambda entry: entry[1], reverse = True):
			sorted_pages.append(SearchResult(key, item))
		return sorted_pages

	def close(self):
		"""
		cleans up resources and write changes to file.
		:return: None.
		"""

		self._word_dictionary.close()
		self._forward_index.close()
		self._reverse_index.close()
		self._session.close()

	def _calculate_page_rank(self):
		"""
		calculates page rank iteratively.
		:return: None
		"""
		try:
			for i in range(self._page_rank_iteration):
				for page_rank in self._session.query(PageRankTracker).all():
					link_weight = 0
					random_weight = 1 - self._dampener
					for referenced_page in self._session.query(ReferenceTracker).filter(
							ReferenceTracker.url == page_rank.url):
						other_url = self._session.query(PageUrlMapper.url).filter(
							PageUrlMapper.id == referenced_page.page_id).one()[0]
						other_page_rank = self._session.query(PageRankTracker).filter(
							PageRankTracker.url == other_url).one()
						link_out_count = \
							self._session.query(PageLinks.count).filter(PageLinks.id == referenced_page.page_id).one()[
								0]
						link_weight += other_page_rank.page_rank / link_out_count
					link_weight = self._dampener * link_weight
					page_rank.page_rank = random_weight + link_weight
					self._session.merge(page_rank)
			self._session.commit()
		except SQLAlchemyError as e:
			raise PageRankPersistException() from e


class TestForwardIndex(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		configure("sqlite:///:memory:")
		Base.metadata.create_all(engine)

	def test_index(self):
		word_dictionary = WordDictionary()
		anchors = [Anchor("Example", "https://www.example.com")]
		headers = [Header(text = "Go to example", size = 1)]
		texts = [TextSection(text = "Go with example")]
		page = PageDocument(doc_id = 1, title = "Test Page", checksum = "12345", url = "https://www.test.com",
		                    anchors = anchors, texts = texts, headers = headers)
		forward_index = ForwardIndex(word_dictionary)
		try:
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
		cleanup()


class TestReverseIndex(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		configure("sqlite:///:memory:")
		Base.metadata.create_all(engine)

	def test_index(self):
		word_dictionary = WordDictionary()

		# set up forward entry
		forward_entry = ForwardIndexEntry(1)
		forward_entry.hits[word_dictionary.get_word_id("Go")] = [Hit(Hit.HEADER_HIT, 0, 0),
		                                                         Hit(Hit.TEXT_HIT, 0, 0)]
		forward_entry.hits[word_dictionary.get_word_id("example")] = [Hit(Hit.HEADER_HIT, 0, 2),
		                                                              Hit(Hit.TEXT_HIT, 0, 2),
		                                                              Hit(Hit.ANCHOR_HIT, 0, 0)]
		session = Session()
		session.add_all(forward_entry.hits[word_dictionary.get_word_id("Go")])
		session.add_all(forward_entry.hits[word_dictionary.get_word_id("example")])
		session.commit()
		reverse_index = ReverseIndex()
		try:
			reverse_index.index(forward_entry)
			reverse_entry_go = reverse_index.get_entry(word_dictionary.get_word_id("go"))
			reverse_entries_example = reverse_index.get_entry(word_dictionary.get_word_id("example"))
			expected_entry_go = ReverseIndexEntry(word_dictionary.get_word_id("go"))
			expected_entry_go.pages[1] = [Hit(Hit.HEADER_HIT, 0, 0), Hit(Hit.TEXT_HIT, 0, 0)]
			expected_entry_example = ReverseIndexEntry(word_dictionary.get_word_id("example"))
			expected_entry_example.pages[1] = [Hit(Hit.HEADER_HIT, 0, 2),
			                                   Hit(Hit.TEXT_HIT, 0, 2),
			                                   Hit(Hit.ANCHOR_HIT, 0, 0)]
			self.assertEqual(expected_entry_go, reverse_entry_go)
			self.assertEqual(expected_entry_example, reverse_entries_example)
		finally:
			reverse_index.close()
			word_dictionary.close()
			session.close()

	@classmethod
	def tearDownClass(cls):
		cleanup()


class TestIndexer(unittest.TestCase):

	def setUp(self):
		configure("sqlite:///:memory:", connect_args = {'check_same_thread': False}, poolclass = StaticPool)
		Base.metadata.create_all(engine)

	@staticmethod
	def load_indexer():
		indexer = Indexer()
		return indexer

	@staticmethod
	def create_simple_multipage_data():
		headers1 = [Header(text = "Page 1 test")]
		texts1 = TextSection(text = "This should be the highest ranked by page rank"), TextSection(
			text = "Welcome to page 1")
		page1 = PageDocument(doc_id = 3, title = "Page 1", checksum = "12345", url = "https://www.page1.com",
		                     texts = texts1, headers = headers1)

		headers2 = [Header(text = "Page 2 test"), Header(text = "References")]
		texts2 = TextSection(text = "This should be the second ranked by page rank"), TextSection(
			text = "Welcome to page 2"), TextSection(text = "Page one is great")
		anchors2 = [Anchor("Page 1", "https://www.page1.com")]
		page2 = PageDocument(doc_id = 1, title = "Page 2", checksum = "67890", url = "https://www.page2.com",
		                     texts = texts2, anchors = anchors2, headers = headers2)

		headers3 = [Header(text = "Page 3 test"), Header(text = "References")]
		texts3 = TextSection(text = "This should be the third ranked by page rank"), TextSection(
			text = "Welcome to page 3"), TextSection(text = "Page two is great"), TextSection(
			text = "Page one is great")
		anchors3 = [Anchor("Page 2", "https://www.page2.com"), Anchor("Page 1", "https://www.page1.com")]
		page3 = PageDocument(doc_id = 2, title = "Page 3", checksum = "09876", url = "https://www.page3.com",
		                     texts = texts3, anchors = anchors3, headers = headers3)
		return page1, page2, page3

	def test_single_entry(self):
		indexer = self.load_indexer()
		anchors = Anchor("Example", "https://www.example.com"), Anchor("Facebook", "https://www.facebook.com")
		headers = Header(text = "Go to example"), Header(text = "Like on facebook")
		texts = TextSection(text = "This is a page used to test the indexer"), TextSection(
			text = "If you like this page, like on Facebook")
		page = PageDocument(doc_id = 1, title = "Test Page", checksum = "12345", url = "https://www.test.com",
		                    anchors = anchors, texts = texts, headers = headers)
		indexer.index(page)
		query_result = indexer.search_by_keywords("test")
		self.assertEqual(1, len(query_result),
		                 "search_by_keywords did not return the single page that it should match")
		self.assertEqual(1, query_result[0].page_id, "search_by_keywords did not maintain the id")
		indexer.close()

	def test_multiple_entry_with_single_word_query(self):
		indexer = self.load_indexer()
		pages = self.create_simple_multipage_data()
		for page in pages:
			indexer.index(page)
		query_result = indexer.search_by_keywords("Page")
		self.assertEqual(3, len(query_result), "search_by_keywords did not return the pages that it should match")
		self.assertEqual(3, query_result[0].page_id, "The page Page 1 should be ranked first")
		self.assertEqual(1, query_result[1].page_id, "The page Page 2 should be ranked second")
		self.assertEqual(2, query_result[2].page_id, "The page Page 3 should be ranked third")
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
		self.assertEqual(1, query_result[0].page_id, "Failed to maintain integrity")
		indexer.close()

	def tearDown(self):
		cleanup()

class TestWordDictionary(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		configure("sqlite:///:memory:")
		Base.metadata.create_all(engine)

	def test_word_to_id(self):
		dictionary = WordDictionary()
		lexicon_id = dictionary.get_word_id("lexicon")
		test_id = dictionary.get_word_id("test")
		url_id = dictionary.get_word_id("https://www.google.com")
		dictionary.close()
		self.assertEqual(1, lexicon_id, "Dictionary not providing id correctly")
		self.assertEqual(2, test_id, "Dictionary not incrementing id correctly")
		self.assertEqual(3, url_id, "Dictionary failed to handle url")

	def test_word_identification(self):
		dictionary = WordDictionary()
		dictionary.add_word("lexicon")
		self.assertEqual(1, dictionary.get_word_id("lexicon"), "Dictionary failed basic retrieval")
		self.assertEqual(1, dictionary.get_word_id("Lexicon"), "Dictionary failed capitalization identification")
		self.assertEqual(1, dictionary.get_word_id("LEXICON"), "Dictionary failed capitalization identification")
		self.assertEqual(1, dictionary.get_word_id("'lexicon'"), "Dictionary failed punctuation identification")
		self.assertEqual(1, dictionary.get_word_id("lexicon,"), "Dictionary failed punctuation identification")
		self.assertEqual(1, dictionary.get_word_id(".lexicon"), "Dictionary failed punctuation identification")

	@classmethod
	def tearDownClass(cls):
		cleanup()
