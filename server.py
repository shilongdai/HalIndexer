import atexit
import json

import pika

import data.web as wb
from index.indexer import Indexer


def handle_crawled_data(chl, method, properties, body):
	crawled_raw = json.loads(body, encoding = "utf8")
	crawled = wb.PageDocument()
	crawled.doc_id = crawled_raw["id"]
	crawled.url = crawled_raw["url"]
	for anchor in crawled_raw["anchors"]:
		anchor_obj = wb.Anchor(anchor["anchorText"], anchor["targetURL"])
		crawled.anchors.append(anchor_obj)
	crawled.texts = crawled_raw["text-sections"]
	for header in crawled_raw["headers"]:
		crawled.headers.append(header["text"])
	crawled.title = crawled_raw["title"]
	crawled.checksum = crawled_raw["checksum"]
	crawled.html = crawled_raw["content"]
	print("Received {0}".format(str(crawled)))
	handle_crawled_data._indexer.index(crawled)
	chl.basic_ack(delivery_tag = method.delivery_tag)


def cleanup():
	print("closing resources")
	handle_crawled_data._indexer.close()


if __name__ == "__main__":
	indexer = Indexer(index_dir = "search_index")
	indexer.load()
	handle_crawled_data._indexer = indexer
	connection = pika.BlockingConnection(pika.ConnectionParameters(host = "localhost"))
	channel = connection.channel()
	channel.queue_declare(queue = "crawledQueue", durable = True)
	channel.basic_consume(handle_crawled_data, queue = "crawledQueue")
	channel.start_consuming()
	atexit.register(cleanup)
