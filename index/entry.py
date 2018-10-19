import struct
import unittest


class Hit:
	"""
	A class representing a hit in the index. As of now, the types of hit includes: text(1), anchor(2), title(3),
	header(4), and url(5). The hit contains the section of the page that the hit occurred on, as well as the position
	within the section. The binary format of the hit is | hit_type: 1 byte| section: 4 bytes| position: 4 bytes|
	"""

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

	def __eq__(self, o: object) -> bool:
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

	def __ne__(self, o: object) -> bool:
		return not self.__eq__(o)

	def __repr__(self):
		return str(self.__dict__)


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
			if self.hits != o.hits:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o: "ForwardIndexEntry") -> bool:
		return not self.__eq__(o)

	def __repr__(self) -> str:
		return str(self.__dict__)


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

		page_id, hit_length = struct.unpack("!IH", data[:6])
		data = data[6:]
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
		return meta_bytes

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
