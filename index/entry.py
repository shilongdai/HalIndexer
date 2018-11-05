import json
import os.path
import struct
import unittest


def dump_dictionary(dictionary, text_file):
	"""
	serializes a dictionary to a text file in json format.
	:param dictionary: the dictionary to serialize
	:param text_file: the text file to dump to.
	:return: None
	"""
	with open(text_file, "w") as dump_file:
		json.dump(dictionary, dump_file)


def load_dictionary(text_file):
	"""
	loads a dictionary dumped by dump_dictionary from a text file.
	:param text_file: the text file to load.
	:return: the dictionary.
	"""
	if not os.path.isfile(text_file):
		return dict()
	with open(text_file, "r") as read_file:
		return json.load(read_file)


class Hit:
	"""
	A class representing a hit in the index. As of now, the types of hit includes: text(1), anchor(2), title(3), header(4),
	url(5), reference(6). The hit contains the section of the page that the hit occurred on, as well as the position
	within the section. The binary format of the hit is | hit_type: 1 byte| section: 4 bytes| position: 4 bytes|
	"""

	TEXT_HIT = 1
	ANCHOR_HIT = 2
	TITLE_HIT = 3
	HEADER_HIT = 4
	URL_HIT = 5
	REFERENCE_HIT = 6

	@classmethod
	def unpack(cls, data):
		"""
		unpacks the binary form of the Hit into its object representation.
		:param data: the binary form of the Hit
		:return: the object representation of the Hit
		"""

		kind, section, position = struct.unpack("!BII", data)
		return cls(kind, section, position)

	def __init__(self, kind, section, position):
		"""
		creates a new Hit object.
		:param kind: the type of the Hit
		:param section: the section where the hit occurred
		:param position: the position of the hit in the section
		"""

		self.kind = kind
		self.section = section
		self.position = position

	def pack(self):
		"""
		packs the object representation of the hit into the binary form.
		:return: the binary representation of the hit.
		"""

		return struct.pack("!BII", self.kind, self.section, self.position)

	def __eq__(self, o: "Hit") -> bool:
		try:
			if not self.kind == o.kind:
				return False
			if not self.section == o.section:
				return False
			if not self.position == o.position:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "Hit") -> bool:
		return not self.__eq__(o)

	def __repr__(self):
		return str(self.__dict__)

	def __hash__(self) -> int:
		kind_hash = 23 * self.kind.__hash__()
		section_hash = 17 * self.kind.__hash__()
		position_hash = 13 * self.position.__hash__()
		return kind_hash * section_hash * position_hash


class ForwardIndexEntry:
	"""
	A class representing a entry in the forward index of the search engine. It maps a document to the word and hits it contains.
	The binary form of the entry is | page-id: 4 bytes| word count: 4 bytes| words...|
	The form of each word in the forward index is: | word-id: 4 bytes| hit count: 2 bytes| hits...|
	The form of hit is described in Hit.
	"""

	@classmethod
	def unpack(cls, data):
		"""
		unpacks a binary form of the ForwardIndexEntry to its object representation.
		:param data: the binary form of the ForwardIndexEntry
		:return: the object representation.
		"""

		page_id, word_counts = struct.unpack("!II", data[:8])
		hits = dict()
		data = data[8:]
		for word_entry in range(0, word_counts):
			word_id, hit_count = struct.unpack("!IH", data[:6])
			data = data[6:]
			hit_list = []
			hits[word_id] = hit_list
			for hit_iter in range(0, hit_count):
				hit_bytes = data[:9]
				hit = Hit.unpack(hit_bytes)
				hit_list.append(hit)
				data = data[9:]
		result = ForwardIndexEntry(page_id)
		result.hits = hits
		return result

	def __init__(self, page_id):
		"""
		creates a new ForwardIndexEntry object
		:param page_id: the id of the page of this entry
		"""

		self.page_id = page_id
		self.hits = {}

	def pack(self):
		"""
		packs a object representation of the ForwardIndexEntry into its binary form.
		:return: the binary form of the ForwardIndexEntry
		"""

		meta_bytes = struct.pack("!II", self.page_id, len(self.hits.keys()))
		for word_id in self.hits:
			hit_list = self.hits[word_id]
			hit_bytes = bytearray()
			for hit in hit_list:
				hit_bytes.extend(hit.pack())
			word_entry_byte = struct.pack("!IH", word_id, len(hit_list))
			meta_bytes += word_entry_byte + hit_bytes
		return meta_bytes

	def __eq__(self, o: "ForwardIndexEntry") -> bool:
		try:
			if self.page_id != o.page_id:
				return False
			if not self._test_hit_equal(self.hits, o.hits):
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "ForwardIndexEntry") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)

	def _test_hit_equal(self, this_hit, other_hit):
		for key, value in this_hit.items():
			if key not in other_hit:
				return False
			this_hit_set = set(value)
			other_hit_set = set(other_hit[key])
			if this_hit_set != other_hit_set:
				return False
		return True


class ReverseIndexEntry:
	"""
	A class representing an entry in the reverse index of the search engine where word->document/hits.
	The binary format of the ReverseIndexEntry is | page-id: 4 bytes| hit count: 2 bytes| hits...|
	The binary format of the hits is described in Hit.
	"""

	@classmethod
	def unpack(cls, data):
		"""
		unpacks the binary form of the ReverseIndexEntry into its object representation.
		:param data: the binary form of the ReverseIndexEntry.
		:return: the object representation.
		"""

		length, page_id, hit_length = struct.unpack("!IIH", data[:10])
		data = data[10:]
		hit_list = list()
		for i in range(hit_length):
			hit = Hit.unpack(data[:9])
			data = data[9:]
			hit_list.append(hit)
		result = ReverseIndexEntry(0, page_id)
		result.hits = hit_list
		return result

	def __init__(self, word_id, page_id):
		"""
		creates a new ReverseIndexEntry
		:param word_id: the id of the word
		:param page_id: the id of the page
		"""

		self.word_id = word_id
		self.page_id = page_id
		self.hits = list()

	def pack(self):
		"""
		packs the object representation of the ReverseIndexEntry into its binary form.
		:return: the binary representation.
		"""

		meta_bytes = struct.pack("!IH", self.page_id, len(self.hits))
		for hit in self.hits:
			meta_bytes = meta_bytes + hit.pack()
		length = len(meta_bytes)
		length_bytes = struct.pack("!I", length)
		return length_bytes + meta_bytes

	def __eq__(self, o: "ReverseIndexEntry") -> bool:
		try:
			if self.page_id != o.page_id:
				return False
			if self.word_id != o.word_id:
				return False
			if self.hits != o.hits:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "ReverseIndexEntry") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)


class LexiconEntry:
	"""
	A class representing a entry in the Lexicon of the indexer. The Lexicon maps every word id to a list of page ids.
	The binary representation of the Lexicon entry is | word-id: 4 bytes| page count: 4 bytes| page id: 4 bytes| page id...|
	"""

	@classmethod
	def unpack(cls, data):
		"""
		unpacks a LexiconEntry from its binary format to its object form.
		:param data: the binary form of the LexiconEntry
		:return: the object representation.
		"""

		entry_len, word_id, page_count = struct.unpack("!III", data[:12])
		data = data[12:]
		format_str = "I" * page_count
		format_str = "!" + format_str
		page_list = struct.unpack(format_str, data)
		result = LexiconEntry(word_id)
		result.pages = list(page_list)
		return result

	def __init__(self, word_id):
		"""
		creates a new LexiconEntry
		:param word_id: the id of the word
		"""

		self.word_id = word_id
		self.pages = []

	def pack(self):
		"""
		packs a LexiconEntry from its object representation to its binary representation.
		:return: the binary representation of the Lexicon entry.
		"""

		format_str = "!II"
		for i in self.pages:
			format_str += "I"
		result = struct.pack(format_str, self.word_id, len(self.pages), *self.pages)
		entry_len = len(result)
		entry_len_bytes = struct.pack("!I", entry_len)
		return entry_len_bytes + result

	def __eq__(self, o: "LexiconEntry") -> bool:
		try:
			if self.word_id != o.word_id:
				return False
			if self.pages != o.pages:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "LexiconEntry") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)


class DictionaryEntry:
	"""
	A simple dictionary entry in the format of key:entry. This class is mostly used by the WordDictionary to store word:id pairs.
	"""

	@classmethod
	def unpack(cls, data):
		"""
		unpacks an entry in the format of key:entry to a DictionaryEntry.
		:param data: the text entry.
		:return: the unpacked entry.
		"""

		parts = data.split(":")
		key = parts[0]
		for i in parts[1:-1]:
			key += ":" + i
		value = parts[-1]
		return cls(key, value)

	def __init__(self, key, value):
		"""
		creates a new DictionaryEntry by specifying the key:value pair.
		:param key: the key of the entry.
		:param value: the value of the entry.
		"""

		self.key = str(key)
		self.value = str(value)

	def pack(self):
		"""
		packs this entry to the key:entry pair format.
		:return: a string in the format of key:entry.
		"""

		return self.key + ":" + self.value

	def __eq__(self, o: "DictionaryEntry") -> bool:
		try:
			if self.key != o.key:
				return False
			if self.value != o.value:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "DictionaryEntry") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)


class WordDictionaryEntry(DictionaryEntry):
	"""
	A DictionaryEntry that stores word and word_id for WordDictionary.
	"""

	def __init__(self, word, word_id):
		DictionaryEntry.__init__(self, word, word_id)

	@property
	def word(self):
		"""
		gets the word represented by the entry.
		:return: the word.
		"""

		return self.key

	@word.setter
	def word(self, word):
		"""
		sets the word represented by the entry.
		:param word: the word
		:return: None.
		"""

		self.key = word

	@property
	def word_id(self):
		"""
		gets the word id mapped by this entry.
		:return: the word id.
		"""

		return int(self.value)

	@word_id.setter
	def word_id(self, word_id):
		"""
		sets the word id mapped by this entry.
		:param word_id: the word id.
		:return: None
		"""

		self.value = word_id


class TestHit(unittest.TestCase):

	def test_packing(self):
		hit = Hit(1, 1, 12)
		packed_bytes = hit.pack()
		expected_bytes = struct.pack("!BII", 1, 1, 12)
		self.assertEqual(expected_bytes, packed_bytes, "The packed bytes does not match the designed format")

	def test_unpacking(self):
		packed_bytes = struct.pack("!BII", 1, 1, 12)
		expected = Hit(1, 1, 12)
		actual = Hit.unpack(packed_bytes)
		self.assertEqual(expected, actual, "Failed to unpack binary data correctly")


class TestForwardEntry(unittest.TestCase):

	def test_packing(self):
		test_entry = ForwardIndexEntry(1)
		test_entry.hits[1] = [Hit(1, 1, 12), Hit(2, 2, 0)]
		test_entry.hits[13] = [Hit(1, 3, 10)]

		meta_bytes = struct.pack("!II", test_entry.page_id, len(test_entry.hits.keys()))
		for word_id in test_entry.hits:
			hit_list = test_entry.hits[word_id]
			hit_bytes = bytearray()
			for hit in hit_list:
				hit_bytes.extend(hit.pack())
			word_entry_byte = struct.pack("!IH", word_id, len(hit_list))
			meta_bytes += word_entry_byte + hit_bytes
		self.assertEqual(meta_bytes, test_entry.pack(), "Failed to pack data into the correct byte format")

	def test_unpacking(self):
		test_entry = ForwardIndexEntry(1)
		test_entry.hits[1] = [Hit(1, 1, 12), Hit(2, 2, 0)]
		test_entry.hits[13] = [Hit(1, 3, 10)]
		packed_bytes = test_entry.pack()
		forward_entry = ForwardIndexEntry.unpack(packed_bytes)
		self.assertEqual(test_entry, forward_entry, "Failed to unpack bytes in the correct format")


class TestReverseEntry(unittest.TestCase):

	def test_packing(self):
		reverse_entry = ReverseIndexEntry(1, 1)
		reverse_entry.hits.append(Hit(1, 1, 12))
		reverse_entry.hits.append(Hit(2, 2, 10))
		reverse_entry.hits.append(Hit(1, 3, 20))
		reverse_entry_bytes = reverse_entry.pack()

		meta_bytes = struct.pack("!IH", reverse_entry.page_id, len(reverse_entry.hits))
		for hit in reverse_entry.hits:
			meta_bytes = meta_bytes + hit.pack()
		meta_bytes = struct.pack("!I", len(meta_bytes)) + meta_bytes

		self.assertEqual(meta_bytes, reverse_entry_bytes, "Reverse entry not packing according to format")

	def test_unpacking(self):
		reverse_entry = ReverseIndexEntry(1, 1)
		reverse_entry.hits.append(Hit(1, 1, 12))
		reverse_entry.hits.append(Hit(2, 2, 10))
		reverse_entry.hits.append(Hit(1, 3, 20))
		reverse_entry_bytes = reverse_entry.pack()

		entry_to_test = ReverseIndexEntry.unpack(reverse_entry_bytes)
		entry_to_test.word_id = 1
		self.assertEqual(reverse_entry, entry_to_test, "Reverse entry not unpacking according to format")


class TestLexiconEntry(unittest.TestCase):

	def test_packing(self):
		lexicon_entry = LexiconEntry(1)
		lexicon_entry.pages.extend([1, 2, 3, 4])
		actual_bytes = lexicon_entry.pack()

		format_str = "!II"
		for i in lexicon_entry.pages:
			format_str += "I"
		expected_bytes = struct.pack(format_str, lexicon_entry.word_id, len(lexicon_entry.pages), *lexicon_entry.pages)
		length = len(expected_bytes)
		length_bytes = struct.pack("!I", length)
		expected_bytes = length_bytes + expected_bytes
		self.assertEqual(expected_bytes, actual_bytes, "LexiconEntry not packing according to the binary format")

	def test_unpacking(self):
		lexicon_entry = LexiconEntry(1)
		lexicon_entry.pages.extend([1, 2, 3, 4])
		lexicon_bytes = lexicon_entry.pack()

		test_entry = LexiconEntry.unpack(lexicon_bytes)
		self.assertEqual(lexicon_entry, test_entry, "LexiconEntry not unpacking according to the binary format")


class TestDictionaryEntry(unittest.TestCase):

	def test_packing(self):
		dic_entry = DictionaryEntry("lexicon", 1)
		dictionary_str = dic_entry.pack()

		expected_str = "lexicon:1"
		self.assertEqual(dictionary_str, expected_str, "Dictionary entry not packing according to format")

	def test_unpacking(self):
		dictionary_str = "1234:test"
		dic_entry = DictionaryEntry.unpack(dictionary_str)
		expected = DictionaryEntry("1234", "test")
		self.assertEqual(expected, dic_entry, "DictionaryEntry not unpacking according to format")


class TestWordDictionaryEntry(unittest.TestCase):

	def test_url(self):
		dictionary_str = "https://www.google.com:1"
		dic_entry = WordDictionaryEntry.unpack(dictionary_str)
		expected = WordDictionaryEntry("https://www.google.com", 1)
		self.assertEqual(expected, dic_entry, "DictionaryEntry failed to handle URL")
