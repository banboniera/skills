"""Background jobs. The worker runs them; web code only enqueues them with `.delay()`."""


class Task:
    def __init__(self, name: str):
        self.name = name

    def delay(self, *args):
        """Enqueue the job for the worker."""


notify_order_ready = Task("notify_order_ready")
