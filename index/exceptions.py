class IndexerException(BaseException):

	def __init__(self, *args, **kwargs):
		BaseException.__init__(self, args, kwargs)


class IndexException(IndexerException):

	def __init__(self, url):
		IndexerException.__init__(self, "Failed to index " + url)
		self.url = url


class PageRankPersistException(IndexerException):

	def __init__(self):
		IndexerException.__init__(self, "Failed to update page rank")


class ForwardIndexException(IndexerException):

	def __init__(self, *args, **kwargs):
		IndexerException.__init__(self, args, kwargs)


class ReverseIndexException(IndexerException):

	def __init__(self, *args, **kwargs):
		IndexerException.__init__(self, args, kwargs)


class HitListPersistException(ForwardIndexException):

	def __init__(self, page_id):
		ForwardIndexException.__init__(self, "Failed to persist hits for " + str(page_id))
		self.page_id = page_id


class ForwardMappingPersistException(ForwardIndexException):

	def __init__(self, page_id):
		ForwardIndexException.__init__(self, "Failed to create forward mappings for " + str(page_id))
		self.page_id = page_id


class PageHitMappingPersistException(ReverseIndexException):

	def __init__(self, word_id):
		ReverseIndexException.__init__(self, "Failed to create page hit mappings for " + str(word_id))
		self.word_id = word_id


class LexiconMappingPersistException(ReverseIndexException):

	def __init__(self, word_id):
		ReverseIndexException.__init__(self, "Failed to create lexicon mappings for " + str(word_id))
		self.word_id = word_id
