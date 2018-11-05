class PageDocument:
	"""
	A data class representing the information crawled from a web page.
	"""

	def __init__(self, doc_id = 0, title = "", checksum = "", url = "", html = "", anchors = (), texts = (),
	             headers = ()):
		"""
		creates a new PageDocument
		:param doc_id: the id of the document in the main repository.
		:param title: the title of the page.
		:param checksum: the checksum of the page.
		:param url: the url of the page.
		:param html: the html of the page.
		:param anchors: the anchors on the page.
		:param texts: the text sections on the page.
		:param headers: the headings on the page.
		"""

		self.doc_id = doc_id
		self.title = title
		self.checksum = checksum
		self.url = url
		self.html = html
		self.anchors = list(anchors)
		self.texts = list(texts)
		self.headers = list(headers)

	def __repr__(self) -> str:
		return str(self.__dict__)


class Anchor:
	"""
	A data class representing the anchor on a webpage.
	"""

	def __init__(self, text, url):
		self.text = text
		self.url = url

	def __repr__(self) -> str:
		return str(self.__dict__)
