from litmuz_service.queue import InMemoryQueue


def test_in_memory_queue_enqueue_and_drain():
    queue = InMemoryQueue()
    queue.enqueue("a")
    queue.enqueue("b")
    assert queue.receive() == ["a", "b"]
    assert queue.receive() == []  # draining empties it
