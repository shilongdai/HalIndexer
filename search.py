import sys

import index.indexer as id

if __name__ == "__main__":
	sys.setrecursionlimit(10000)
	term = sys.argv[1]
	indexer = id.Indexer(index_dir = "search_index", dampener = 0.85, page_rank_iteration = 100)
	indexer.load()
	results = indexer.search_by_keywords(term)
	for result in results:
		print("Found id {}, page rank {}\n".format(result.page_id, result.page_rank))
