import json

def handler(event, context):
    print("lambda_b received event:")
    print(json.dumps(event))

    return {"status": "processed"}