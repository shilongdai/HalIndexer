import pika


def handle_crawled_data(channel, method, properties, body):
	print("Received {0}".format(body))
	channel.basic_ack(delivery_tag = method.delivery_tag)


if __name__ == "__main__":
	connection = pika.BlockingConnection(pika.ConnectionParameters(host = "localhost"))
	channel = connection.channel()
	channel.queue_declare(queue = "crawledQueue", durable = True)
	channel.basic_consume(handle_crawled_data, queue = "crawledQueue")
	channel.start_consuming()
