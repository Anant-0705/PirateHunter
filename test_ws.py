import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/ws"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Sending subscribe...")
            await websocket.send(json.dumps({
                "action": "subscribe",
                "match_ids": ["00000000-0000-0000-0000-000000000001"]
            }))
            print("Sent subscribe. Waiting for messages...")
            while True:
                msg = await websocket.recv()
                print(f"Received: {msg}")
    except Exception as e:
        print(f"Failed to connect or error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
