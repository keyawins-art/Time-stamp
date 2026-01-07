from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import csv
import io
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Database configuration - uses PostgreSQL on Render, SQLite locally
# Database configuration
database_url = os.environ.get('DATABASE_URL', 'sqlite:///timestamp.db')
# Render provides postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Session model
class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), nullable=False, index=True)
    session_start = db.Column(db.DateTime, nullable=False)
    last_heartbeat = db.Column(db.DateTime, nullable=False)
    session_end = db.Column(db.DateTime, nullable=True)
    runtime_seconds = db.Column(db.Integer, default=0)
    date = db.Column(db.String(10), nullable=False, index=True)  # YYYY-MM-DD
    status = db.Column(db.String(20), default='active')  # 'active' or 'completed'
    device_session_id = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'session_number': self.device_session_id,
            'device_id': self.device_id,
            'session_start': self.session_start.strftime('%Y-%m-%d %H:%M:%S'),
            'last_heartbeat': self.last_heartbeat.strftime('%Y-%m-%d %H:%M:%S'),
            'session_end': self.session_end.strftime('%Y-%m-%d %H:%M:%S') if self.session_end else None,
            'runtime_seconds': self.runtime_seconds,
            'runtime_formatted': self.format_runtime(),
            'date': self.date,
            'status': self.status
        }
    
    def format_runtime(self):
        """Format runtime in human-readable format"""
        hours = self.runtime_seconds // 3600
        minutes = (self.runtime_seconds % 3600) // 60
        seconds = self.runtime_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

# Create tables
with app.app_context():
    db.create_all()

def check_stale_sessions():
    """Mark sessions as completed if no heartbeat for 120 seconds"""
    threshold = datetime.utcnow() - timedelta(seconds=120)
    stale_sessions = Session.query.filter(
        Session.status == 'active',
        Session.last_heartbeat < threshold
    ).all()
    
    for session in stale_sessions:
        missed_seconds = int((datetime.utcnow() - session.last_heartbeat).total_seconds())
        print(f"DEBUG: Marking session {session.id} ({session.device_id}) as stale. Last heartbeat was {missed_seconds}s ago.")
        
        session.status = 'completed'
        session.session_end = session.last_heartbeat
        session.runtime_seconds = int((session.session_end - session.session_start).total_seconds())
        log_session_to_csv(session)
    
    if stale_sessions:
        db.session.commit()

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

def log_session_to_csv(session):
    """Log session details to a daily CSV file"""
    try:
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        file_path = log_dir / f"sessions_{session.date}.csv"
        file_exists = file_path.exists()
        
        with open(file_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date', 'Device ID', 'Session ID', 'Start Time', 'End Time', 'Runtime', 'Status'])
            
            writer.writerow([
                session.date,
                session.device_id,
                f"#{session.device_session_id}",
                session.session_start.strftime('%H:%M:%S'),
                session.session_end.strftime('%H:%M:%S') if session.session_end else 'N/A',
                session.format_runtime(),
                session.status
            ])
        print(f"DEBUG: Logged session {session.id} to {file_path}")
    except Exception as e:
        print(f"ERROR: Failed to log session to CSV: {str(e)}")

@app.route('/')
def index():
    """Render the device list homepage"""
    return render_template('index.html')

@app.route('/device/<device_id>')
def device_details(device_id):
    """Render device details page"""
    return render_template('device_details.html', device_id=device_id)

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Start a new session"""
    try:
        data = request.json
        device_id = data.get('device_id', 'unknown')
        
        now = datetime.utcnow()
        today = now.strftime('%Y-%m-%d')
        
        # Close any existing active sessions for this device
        existing_active = Session.query.filter(
            Session.device_id == device_id,
            Session.status == 'active'
        ).all()
        
        for session in existing_active:
            session.status = 'completed'
            session.session_end = session.last_heartbeat
            session.runtime_seconds = int((session.session_end - session.session_start).total_seconds())
        
        # Calculate next session ID for this device for TODAY
        last_session_today = Session.query.filter_by(device_id=device_id, date=today).order_by(Session.device_session_id.desc()).first()
        next_session_id = (last_session_today.device_session_id + 1) if last_session_today and last_session_today.device_session_id else 1

        # Create new session
        new_session = Session(
            device_id=device_id,
            device_session_id=next_session_id,
            session_start=now,
            last_heartbeat=now,
            date=today,
            status='active'
        )
        db.session.add(new_session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Session started',
            'session_id': new_session.id,
            'data': new_session.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/heartbeat', methods=['POST'])
def heartbeat():
    """Update session heartbeat"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400
        
        session = Session.query.get(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        session.last_heartbeat = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Heartbeat updated'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/stop', methods=['POST'])
def stop_session():
    """Stop a session"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'session_id required'}), 400
        
        session = Session.query.get(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        now = datetime.utcnow()
        session.session_end = now
        session.status = 'completed'
        session.runtime_seconds = int((now - session.session_start).total_seconds())
        db.session.commit()
        
        log_session_to_csv(session)
        
        return jsonify({
            'success': True,
            'message': 'Session stopped',
            'data': session.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices with today's stats"""
    try:
        check_stale_sessions()  # Check for stale sessions first
        
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Get all unique devices
        devices = db.session.query(Session.device_id).distinct().all()
        device_list = []
        
        for (device_id,) in devices:
            # Get today's sessions for this device
            today_sessions = Session.query.filter(
                Session.device_id == device_id,
                Session.date == today
            ).all()
            
            # Calculate total runtime for today
            total_runtime = sum(s.runtime_seconds for s in today_sessions if s.status == 'completed')
            
            # Check if any active session
            active_session = Session.query.filter(
                Session.device_id == device_id,
                Session.status == 'active'
            ).first()
            
            # If active session exists, add current runtime
            if active_session:
                current_runtime = int((datetime.utcnow() - active_session.session_start).total_seconds())
                total_runtime += current_runtime
                status = 'running'
                last_active = active_session.last_heartbeat
            else:
                status = 'stopped'
                # Get last session
                last_session = Session.query.filter(
                    Session.device_id == device_id
                ).order_by(Session.last_heartbeat.desc()).first()
                last_active = last_session.last_heartbeat if last_session else None
            
            # Format runtime
            hours = total_runtime // 3600
            minutes = (total_runtime % 3600) // 60
            if hours > 0:
                runtime_formatted = f"{hours}h {minutes}m"
            elif minutes > 0:
                runtime_formatted = f"{minutes}m"
            else:
                runtime_formatted = f"{total_runtime}s"
            
            device_list.append({
                'device_id': device_id,
                'status': status,
                'today_runtime_seconds': total_runtime,
                'today_runtime_formatted': runtime_formatted,
                'session_count_today': len(today_sessions),
                'last_active': last_active.strftime('%Y-%m-%d %H:%M:%S') if last_active else None
            })
        
        # Sort by status (running first) then by device_id
        device_list.sort(key=lambda x: (0 if x['status'] == 'running' else 1, x['device_id']))
        
        return jsonify({
            'success': True,
            'devices': device_list,
            'count': len(device_list)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/<device_id>/sessions', methods=['GET'])
def get_device_sessions(device_id):
    """Get all sessions for a device"""
    try:
        check_stale_sessions()
        
        date = request.args.get('date')  # Optional date filter (YYYY-MM-DD)
        
        query = Session.query.filter(Session.device_id == device_id)
        
        if date:
            query = query.filter(Session.date == date)
        
        sessions = query.order_by(Session.session_start.desc()).all()
        
        return jsonify({
            'success': True,
            'device_id': device_id,
            'sessions': [s.to_dict() for s in sessions],
            'count': len(sessions)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/<device_id>/daily/<date>', methods=['GET'])
def get_daily_summary(device_id, date):
    """Get daily summary for a device"""
    try:
        check_stale_sessions()
        
        sessions = Session.query.filter(
            Session.device_id == device_id,
            Session.date == date
        ).all()
        
        total_runtime = sum(s.runtime_seconds for s in sessions if s.status == 'completed')
        
        # If there's an active session today, add current runtime
        active_session = next((s for s in sessions if s.status == 'active'), None)
        if active_session:
            current_runtime = int((datetime.utcnow() - active_session.session_start).total_seconds())
            total_runtime += current_runtime
        
        hours = total_runtime // 3600
        minutes = (total_runtime % 3600) // 60
        
        return jsonify({
            'success': True,
            'device_id': device_id,
            'date': date,
            'total_runtime_seconds': total_runtime,
            'total_runtime_formatted': f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m",
            'session_count': len(sessions),
            'sessions': [s.to_dict() for s in sessions]
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/<device_id>/history', methods=['GET'])
def get_device_history(device_id):
    """Get historical daily runtime for a device (last 30 days)"""
    try:
        check_stale_sessions()
        
        # Get date range from query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        if start_date_str and end_date_str:
            # Custom range
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            # Default: Since 2026-01-01
            end_date = datetime.utcnow()
            start_date = datetime(2026, 1, 1)
        
        print(f"DEBUG: Fetching history for {device_id} starting from {start_date}")
        
        # Get all sessions for this device in date range
        # Note: end_date comparison needs to handle time, so we convert dates to strings for comparison
        sessions = Session.query.filter(
            Session.device_id == device_id,
            Session.date >= start_date.strftime('%Y-%m-%d'),
            Session.date <= end_date.strftime('%Y-%m-%d')
        ).all()
        
        # Group by date and calculate total runtime
        daily_data = {}
        for session in sessions:
            date = session.date
            if date not in daily_data:
                daily_data[date] = 0
            
            if session.status == 'completed':
                daily_data[date] += session.runtime_seconds
            elif session.status == 'active':
                # Add current runtime for active sessions
                current_runtime = int((datetime.utcnow() - session.session_start).total_seconds())
                daily_data[date] += current_runtime
        
        # Create list of all dates in range (fill missing dates with 0)
        history = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            runtime_seconds = daily_data.get(date_str, 0)
            runtime_hours = round(runtime_seconds / 3600, 2)  # Convert to hours
            
            history.append({
                'date': date_str,
                'runtime_seconds': runtime_seconds,
                'runtime_hours': runtime_hours
            })
            current_date += timedelta(days=1)
        
        return jsonify({
            'success': True,
            'device_id': device_id,
            'history': history
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/device/<device_id>/export')
def export_device_csv(device_id):
    """Export all session data for a device as CSV"""
    try:
        # Get all sessions for this device
        sessions = Session.query.filter_by(device_id=device_id).order_by(Session.date.desc(), Session.session_start.desc()).all()
        
        # Group by date to calculate day totals
        daily_totals = {}
        for s in sessions:
            if s.date not in daily_totals:
                daily_totals[s.date] = 0
            
            if s.status == 'completed':
                daily_totals[s.date] += s.runtime_seconds
            elif s.status == 'active':
                current_runtime = int((datetime.utcnow() - s.session_start).total_seconds())
                daily_totals[s.date] += current_runtime
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow(['Date', 'Session ID', 'Start Time', 'End Time', 'Runtime', 'Status', 'Day Total (HH:MM)'])
        
        for s in sessions:
            # Format Day Total only once per date
            dt_seconds = daily_totals.get(s.date, 0)
            dt_hours = dt_seconds // 3600
            dt_minutes = (dt_seconds % 3600) // 60
            day_total_str = f"{dt_hours}h {dt_minutes}m"
            
            writer.writerow([
                s.date,
                f"#{s.device_session_id}",
                s.session_start.strftime('%H:%M:%S'),
                s.session_end.strftime('%H:%M:%S') if s.session_end else 'Active',
                s.format_runtime() if hasattr(s, 'format_runtime') else 'N/A',
                s.status.capitalize(),
                day_total_str
            ])
        
        output.seek(0)
        from flask import make_response
        res = make_response(output.getvalue())
        res.headers["Content-Disposition"] = f"attachment; filename={device_id}_history.csv"
        res.headers["Content-type"] = "text/csv"
        return res

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
