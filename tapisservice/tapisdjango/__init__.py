# can use the django request object? problem seems to be the request object is not available
# to all modules...
import threading


request_thread_local = threading.local()

