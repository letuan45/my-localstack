import json

def handler(event, context):
    event = json.dumps(event)
    print(f"Lambda b received event: {event}")

    return {"status": "processed"}