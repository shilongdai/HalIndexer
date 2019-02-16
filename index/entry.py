import json
import os.path

import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


def dump_dictionary(dictionary, text_file):
	"""
	serializes a dictionary to a text file in json format.
	:param dictionary: the dictionary to serialize
	:param text_file: the text file to dump to.
	:return: None
	"""
	with open(text_file, "w") as dump_file:
		json.dump(dictionary, dump_file)


def load_dictionary(text_file, key_converter=str, value_converter=str):
	"""
	loads a dictionary dumped by dump_dictionary from a text file.
	:param text_file: the text file to load.
	:param key_converter: the converter to convert the key to the right type from string
	:param value_converter: the converter to convert the value to the right type from string
	:return: the dictionary.
	"""
	if not os.path.isfile(text_file):
		return dict()
	with open(text_file, "r") as read_file:
		buffer = json.load(read_file)
		result = {key_converter(key): value_converter(value) for key, value in buffer.items()}
		return result


Base = declarative_base()


class PageDocument(Base):
	"""
	A data class representing the information crawled from a web page.
	"""
	__tablename__ = "Document"
	doc_id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	title = sa.Column("title", sa.String(500), nullable=False)
	url = sa.Column("url", sa.String(500), nullable=False)
	content = sa.Column("content", sa.Binary(2000000), nullable=False)
	checksum = sa.Column("checksum", sa.Binary(128), nullable=False)
	anchors = relationship("Anchor")
	headers = relationship("Header")
	texts = relationship("TextSection")

	def __init__(self, doc_id=0, title="", checksum=b"", url="", content=b"", anchors=(), texts=(),
	             headers=()):
		"""
		creates a new PageDocument
		:param doc_id: the id of the document in the main repository.
		:param title: the title of the page.
		:param checksum: the checksum of the page.
		:param url: the url of the page.
		:param html: the html of the page.
		:param anchors: the anchors on the page.
		:param texts: the text sectins on the page.
		:param headers: the headings on the page.
		"""

		self.doc_id = doc_id
		self.title = title
		self.checksum = checksum
		self.url = url
		self.content = content
		self.anchors.extend(anchors)
		self.texts.extend(texts)
		self.headers.extend(headers)

	def __repr__(self) -> str:
		return str(self.__dict__)


class Anchor(Base):
	"""
	A data class representing the anchor on a webpage.
	"""

	__tablename__ = "Anchor"
	doc_id = sa.Column("doc_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("Document.id"))
	text = sa.Column("text", sa.String(500), nullable=False)
	url = sa.Column("url", sa.String(500), nullable=False)
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)

	def __init__(self, text, url):
		self.text = text
		self.url = url

	def __repr__(self) -> str:
		return str(self.__dict__)


class Header(Base):
	__tablename__ = "Header"
	doc_id = sa.Column("doc_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("Document.id"))
	text = sa.Column("text", sa.String(500), nullable=False)
	size = sa.Column("size", sa.Integer, nullable=False)
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)

	def __init__(self, size=1, text=""):
		self.text = text
		self.size = size

	def __repr__(self):
		return str(self.__dict__)


class TextSection(Base):
	__tablename__ = "TextSection"
	doc_id = sa.Column("doc_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), sa.ForeignKey("Document.id"))
	text = sa.Column("text", sa.String(5000), nullable=False)
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)

	def __init__(self, text):
		self.text = text


class Hit(Base):
	"""
	A class representing a hit in the index. As of now, the types of hit includes: text(1), anchor(2), title(3), header(4),
	url(5), reference(6). The hit contains the section of the page that the hit occurred on, as well as the position
	within the section.
	"""

	TEXT_HIT = 1
	ANCHOR_HIT = 2
	TITLE_HIT = 3
	HEADER_HIT = 4
	URL_HIT = 5
	REFERENCE_HIT = 6

	__tablename__ = "Hit"
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	kind = sa.Column("kind", sa.SmallInteger)
	section = sa.Column("section", sa.Integer)
	position = sa.Column("position", sa.Integer)

	def __init__(self, kind, section, position):
		self.kind = kind
		self.section = section
		self.position = position

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
		return str({"kind": self.kind, "section": self.section, "position": self.position})


class WordHitMapper(Base):
	__tablename__ = "WordHitMapper"
	entry_id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	word_id = sa.Column("word_id", sa.BigInteger)
	hit_id = sa.Column("hit_id", sa.BigInteger)

	def __init__(self, word_id, hit_id):
		self.word_id = word_id
		self.hit_id = hit_id

	def __eq__(self, other: "WordHitMapper"):
		try:
			if not self.word_id == other.word_id:
				return False
			if not self.hit_id == other.hit_id:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)


class ForwardMapper(Base):
	__tablename__ = "ForwardMapper"
	entry_id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	page_id = sa.Column("page_id", sa.BigInteger)
	word_id = sa.Column("word_id", sa.BigInteger)

	def __init__(self, page_id, word_id):
		self.page_id = page_id
		self.word_id = word_id

	def __eq__(self, other):
		try:
			if not self.page_id == other.page_id:
				return False
			if not self.word_id == other.word_id:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)


class ForwardIndexEntry:
	"""
	A class representing a entry in the forward index of the search engine. It maps a document to the word and hits it contains.
	"""

	def __init__(self, page_id):
		"""
		creates a new ForwardIndexEntry object
		:param page_id: the id of the page of this entry
		"""

		self.page_id = page_id
		self.hits = {}

	def __repr__(self) -> str:
		return str(self.__dict__)

	def __eq__(self, other):
		try:
			if self.page_id != other.page_id:
				return False
			if self.hits != other.hits:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)


class PageHitMapper(Base):
	__tablename__ = "PageHitMapper"
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	page_id = sa.Column("page_id", sa.BigInteger)
	hit_id = sa.Column("hit_id", sa.BigInteger)

	def __init__(self, page_id, hit_id):
		self.page_id = page_id
		self.hit_id = hit_id

	def __eq__(self, o) -> bool:
		try:
			if self.id != o.id:
				return False
			if not self.page_id == o.page_id:
				return False
			if not self.hit_id == o.hit_id:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o) -> bool:
		return not self.__eq__(o)

	def __repr__(self):
		return str(self.__dict__)


class LexiconMapper(Base):
	__tablename__ = "LexiconMapper"
	entry_id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	word_id = sa.Column("word_id", sa.BigInteger)
	page_hit_mapper_id = sa.Column("entry_id", sa.BigInteger)

	def __init__(self, word_id, page_hit_mapper_id):
		self.word_id = word_id
		self.page_hit_mapper_id = page_hit_mapper_id

	def __eq__(self, o) -> bool:
		try:
			if self.word_id != o.word_id:
				return False
			if not self.page_hit_mapper_id == o.page_hit_mapper_id:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o) -> bool:
		return not self.__eq__(o)

	def __repr__(self):
		return str(self.__dict__)


class ReverseIndexEntry:

	def __init__(self, word_id):
		self.word_id = word_id
		self.pages = {}

	def __repr__(self):
		return str(self.__dict__)

	def __eq__(self, o):
		try:
			if self.word_id != o.word_id:
				return False
			if not self.pages == o.pages:
				return False
		except AttributeError:
			return False
		return True


class WordDictionaryEntry(Base):
	__tablename__ = "WordDictionary"
	word = sa.Column("word", sa.String(500), unique=True)
	word_id = sa.Column("word_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True,
	                    autoincrement=True)

	def __init__(self, word):
		self.word = word

	def __eq__(self, o) -> bool:
		try:
			if self.word_id != o.word_id:
				return False
			if not self.word == o.word:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, o) -> bool:
		return not self.__eq__(o)

	def __repr__(self):
		return str(self.__dict__)


class PageLinks(Base):
	__tablename__ = "PageLinks"
	id = sa.Column("page_id", sa.BigInteger, primary_key=True, autoincrement=False)
	count = sa.Column("link_out", sa.BigInteger)

	def __init__(self, id=-1, count=0):
		self.id = id
		self.count = count

	def __eq__(self, other):
		try:
			if self.id != other.id:
				return False
			if self.count != other.count:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)


class PageUrlMapper(Base):
	__tablename__ = "PageUrlMapper"
	id = sa.Column("page_id", sa.BigInteger, primary_key=True, autoincrement=False)
	url = sa.Column("url", sa.String(500), unique=True)

	def __init__(self, id=-1, url=""):
		self.id = id
		self.url = url

	def __eq__(self, other):
		try:
			if self.id != other.id:
				return False
			if self.url != other.url:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)


class ReferenceTracker(Base):
	__tablename__ = "ReferenceTracker"
	id = sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True)
	page_id = sa.Column("page_id", sa.BigInteger)
	url = sa.Column("url", sa.String(500))

	def __init__(self, page_id=-1, url=""):
		self.page_id = page_id
		self.url = url

	def __eq__(self, other):
		try:
			if self.page_id != other.page_id:
				return False
			if self.url != other.url:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)


class PageRankTracker(Base):
	__tablename__ = "PageRank"
	url = sa.Column("url", sa.String(500), primary_key=True)
	page_rank = sa.Column("page_rank", sa.Float)

	def __init__(self, url="", page_rank=0):
		self.url = url
		self.page_rank = page_rank

	def __eq__(self, other):
		try:
			if self.url != other.url:
				return False
			if self.page_rank != other.page_rank:
				return False
		except AttributeError:
			return False
		return True

	def __ne__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return str(self.__dict__)
