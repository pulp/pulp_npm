import json
import sys

secrets = json.loads(sys.argv[1])
print(secrets.keys())

with open(".env", "w") as dotenv:
    for key, value in secrets.items():
        dotenv.write(f"{key}={value}")
