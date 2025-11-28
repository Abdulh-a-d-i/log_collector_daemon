#!/usr/bin/env python3
# telemetry_ws.py
"""
WebSocket server for streaming telemetry data to connected clients.
Similar to livelogs.py but for system telemetry metrics.
"""
import asyncio
import websockets
import json
import signal
import sys
import argparse
from datetime import datetime
from telemetry_collector import TelemetryCollector

class TelemetryWebSocketServer:
    def __init__(self, node_id: str, port: int, interval: int = 60):
        self.node_id = node_id
        self.port = port
        self.interval = interval
        self.clients = set()
        self.collector = None
        self.running = False
        self.broadcast_task = None
        
    async def register(self, websocket):
        """Register a new client connection"""
        self.clients.add(websocket)
        print(f"[telemetry-ws] Client connected. Total clients: {len(self.clients)}")
        
    async def unregister(self, websocket):
        """Unregister a client connection"""
        self.clients.discard(websocket)
        print(f"[telemetry-ws] Client disconnected. Total clients: {len(self.clients)}")
        
    async def send_to_client(self, websocket, message):
        """Send message to a specific client with error handling"""
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            await self.unregister(websocket)
        except Exception as e:
            print(f"[telemetry-ws] Error sending to client: {e}")
            await self.unregister(websocket)
            
    async def broadcast_telemetry(self):
        """Continuously collect and broadcast telemetry to all connected clients"""
        print(f"[telemetry-ws] Starting telemetry broadcast loop (interval: {self.interval}s)")
        
        while self.running:
            try:
                if self.clients:
                    # Collect metrics
                    metrics = self.collector.collect_all_metrics()
                    message = json.dumps(metrics)
                    
                    # Send to all connected clients
                    if self.clients:
                        await asyncio.gather(
                            *[self.send_to_client(client, message) for client in self.clients],
                            return_exceptions=True
                        )
                        print(f"[telemetry-ws] Broadcasted metrics to {len(self.clients)} client(s)")
                
                # Wait for next interval
                await asyncio.sleep(self.interval)
                
            except Exception as e:
                print(f"[telemetry-ws] Error in broadcast loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
                
    async def handler(self, websocket, path):
        """Handle individual WebSocket connections"""
        await self.register(websocket)
        
        try:
            # Send initial connection confirmation
            welcome = {
                "type": "connection",
                "status": "connected",
                "node_id": self.node_id,
                "interval": self.interval,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            await websocket.send(json.dumps(welcome))
            
            # Keep connection alive and handle incoming messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    # Handle client commands
                    if data.get("command") == "get_metrics":
                        # Send immediate metrics on demand
                        metrics = self.collector.collect_all_metrics()
                        await websocket.send(json.dumps(metrics))
                        
                    elif data.get("command") == "ping":
                        pong = {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                        await websocket.send(json.dumps(pong))
                        
                except json.JSONDecodeError:
                    print(f"[telemetry-ws] Invalid JSON received from client")
                except Exception as e:
                    print(f"[telemetry-ws] Error handling message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[telemetry-ws] Connection error: {e}")
        finally:
            await self.unregister(websocket)
            
    async def start_server(self):
        """Start the WebSocket server"""
        self.running = True
        
        # Initialize telemetry collector (without auto-sending to API)
        self.collector = TelemetryCollector(
            api_url="",  # No API URL needed for WS mode
            node_id=self.node_id,
            interval=self.interval
        )
        
        # Start the broadcast task
        self.broadcast_task = asyncio.create_task(self.broadcast_telemetry())
        
        # Start WebSocket server
        async with websockets.serve(self.handler, "0.0.0.0", self.port):
            print(f"[telemetry-ws] Server started on ws://0.0.0.0:{self.port}")
            print(f"[telemetry-ws] Node ID: {self.node_id}")
            print(f"[telemetry-ws] Broadcast interval: {self.interval}s")
            
            # Run forever
            await asyncio.Future()  # Run forever
            
    def stop(self):
        """Stop the server"""
        print("[telemetry-ws] Shutting down...")
        self.running = False
        if self.broadcast_task:
            self.broadcast_task.cancel()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\n[telemetry-ws] Received shutdown signal")
    sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="WebSocket server for streaming telemetry data"
    )
    parser.add_argument(
        "node_id",
        help="Node identifier"
    )
    parser.add_argument(
        "port",
        type=int,
        help="WebSocket port to listen on"
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        help="Telemetry collection interval in seconds (default: 60)"
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start server
    server = TelemetryWebSocketServer(
        node_id=args.node_id,
        port=args.port,
        interval=args.interval
    )
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\n[telemetry-ws] Interrupted by user")
    except Exception as e:
        print(f"[telemetry-ws] Fatal error: {e}")
    finally:
        server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[telemetry-ws] Exiting...")
        sys.exit(0)
