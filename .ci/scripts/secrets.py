import json
import sys

secrets = json.loads(sys.argv[1])
dotenv_path = sys.argv[2]

with open(dotenv_path, "a") as dotenv:
    for key, value in secrets.items():
        print(f"Setting {key} ...")
        dotenv.write(f"{key}={value}")
