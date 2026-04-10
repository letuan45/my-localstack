import logging
from common.log_handler import OtelLogHandler


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(OtelLogHandler())