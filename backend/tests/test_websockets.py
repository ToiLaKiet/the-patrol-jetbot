import json

def test_web_websocket_connection(client):
    with client.websocket_connect("/ws/web") as ws:
        # Initial state should be received
        data = ws.receive_text()
        msg = json.loads(data)
        assert msg["type"] == "INITIAL_STATE"
        assert "robot" in msg["data"]

        # Send ping
        ws.send_text(json.dumps({"action": "PING"}))
        response = ws.receive_text()
        pong = json.loads(response)
        assert pong["type"] == "PONG"

def test_robot_websocket_connection(client):
    with client.websocket_connect("/ws/robot") as ws:
        # Acknowledge connection
        data = ws.receive_text()
        msg = json.loads(data)
        assert msg["action"] == "CONNECTED"

        # Send heartbeat
        ws.send_text(json.dumps({"type": "HEARTBEAT"}))
        ack = ws.receive_text()
        ack_msg = json.loads(ack)
        assert ack_msg["action"] == "HEARTBEAT_ACK"
