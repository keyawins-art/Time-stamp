# -*- coding: utf-8 -*-
import requests
import time
from datetime import datetime
import sys
import io
import atexit

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Configuration
SERVER_URL = "http://localhost:5000"  # Change this to your Render URL after deployment
# Example: SERVER_URL = "https://timestamp-logger.onrender.com"

HEARTBEAT_INTERVAL = 10  # Send heartbeat every 10 seconds

# SET YOUR CUSTOM DEVICE ID HERE
DEVICE_ID = "PC-1"  # Change this to identify your device (e.g., "Office-PC", "Home-Laptop", "Remote-Server")

# Global session ID
session_id = None

def start_session():
    """Start a new session on the server"""
    try:
        payload = {
            'device_id': DEVICE_ID
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/session/start",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 201:
            data = response.json()
            session_id = data.get('session_id')
            print(f"✓ Session started | ID: {session_id}")
            return session_id
        else:
            print(f"✗ Failed to start session: {response.status_code}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"✗ Connection failed: Cannot reach {SERVER_URL}")
        return None
    except Exception as e:
        print(f"✗ Error starting session: {str(e)}")
        return None

def send_heartbeat(session_id):
    """Send heartbeat to keep session alive"""
    try:
        payload = {
            'session_id': session_id
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/session/heartbeat",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"✗ Heartbeat failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"✗ Connection lost")
        return False
    except Exception as e:
        print(f"✗ Heartbeat error: {str(e)}")
        return False

def stop_session(session_id):
    """Stop the session on the server"""
    if not session_id:
        return
    
    try:
        payload = {
            'session_id': session_id
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/session/stop",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            runtime = data.get('data', {}).get('runtime_formatted', 'unknown')
            print(f"\n✓ Session stopped | Runtime: {runtime}")
        else:
            print(f"\n✗ Failed to stop session: {response.status_code}")
            
    except Exception as e:
        print(f"\n✗ Error stopping session: {str(e)}")

def cleanup_handler():
    """Handle cleanup on exit"""
    global session_id
    if session_id:
        stop_session(session_id)

# Register cleanup handler for normal exit only
atexit.register(cleanup_handler)

def main():
    """Main loop to maintain session"""
    global session_id
    
    print("=" * 60)
    print("🕐 SESSION TRACKER CLIENT")
    print("=" * 60)
    print(f"Server URL: {SERVER_URL}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Heartbeat Interval: {HEARTBEAT_INTERVAL} seconds")
    print("=" * 60)
    print("\nStarting session... (Press Ctrl+C to stop)\n")
    sys.stdout.flush()
    
    # Start session
    session_id = start_session()
    
    if not session_id:
        print("\n❌ Failed to start session. Exiting...")
        return
    
    start_time = datetime.now()
    heartbeat_count = 0
    consecutive_failures = 0
    max_failures = 3
    
    print(f"⏱️  Session active | Started at {start_time.strftime('%H:%M:%S')}\n")
    sys.stdout.flush()
    
    while True:
        try:
            time.sleep(HEARTBEAT_INTERVAL)
            
            success = send_heartbeat(session_id)
            heartbeat_count += 1
            
            if success:
                consecutive_failures = 0
                elapsed = datetime.now() - start_time
                hours = int(elapsed.total_seconds() // 3600)
                minutes = int((elapsed.total_seconds() % 3600) // 60)
                seconds = int(elapsed.total_seconds() % 60)
                
                if hours > 0:
                    runtime_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    runtime_str = f"{minutes}m {seconds}s"
                else:
                    runtime_str = f"{seconds}s"
                
                print(f"💓 Heartbeat #{heartbeat_count} | Runtime: {runtime_str}")
                sys.stdout.flush()
            else:
                consecutive_failures += 1
                
            # If too many consecutive failures, exit
            if consecutive_failures >= max_failures:
                print(f"\n⚠ Too many heartbeat failures. Exiting...")
                break
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping session...")
            stop_session(session_id)
            sys.exit(0)

if __name__ == "__main__":
    # Validate server URL
    if SERVER_URL == "http://localhost:5000":
        print("\n⚠ WARNING: Using localhost URL. Update SERVER_URL to your Render URL for remote access!\n")
    
    main()