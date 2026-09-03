import multiprocessing
import os

workers = int(
    os.environ.get(
        "WEB_CONCURRENCY",
        multiprocessing.cpu_count(),
    )
)

worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
proxy_protocol = True
forwarded_allow_ips = "*"
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
keepalive = 30
graceful_timeout = 30
timeout = 120
