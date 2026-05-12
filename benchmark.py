import timeit

setup_code = """
import logging
import sys
from loguru import logger
logger.remove()  # Remove all handlers to avoid printing

from src.aradhya.utils.json_extractor import extract_json_from_llm_response
response = '''
Here is some text before the json.
```json
{"key1": "value1", "key2": {"nested": "value2"}}
```
And some text after.
```
{"another": "json"}
```
`{"inline": "json"}`
'''
"""

test_code = """
try:
    extract_json_from_llm_response(response)
except Exception:
    pass
"""

iterations = 100000
time_taken = timeit.timeit(test_code, setup=setup_code, number=iterations)
print(f"Time for {iterations} iterations: {time_taken:.4f} seconds")
