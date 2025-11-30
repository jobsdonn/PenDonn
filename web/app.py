"""
PenDonn Web Interface
Flask web application for controlling the system
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load configuration
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

app.config['SECRET_KEY'] = config['web']['secret_key']

# Initialize database
db = Database(config['database']['path'])


@app.route('/')
def index():
    """Dashboard page"""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Get overall system status"""
    try:
        stats = db.get_statistics()
        
        # Get running status (check if main process is running)
        import subprocess
        result = subprocess.run(['systemctl', 'is-active', 'pendonn'], 
                              capture_output=True, text=True)
        daemon_running = result.stdout.strip() == 'active'
        
        return jsonify({
            'success': True,
            'status': {
                'daemon_running': daemon_running,
                'statistics': stats,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/networks')
def get_networks():
    """Get discovered networks - only show recently seen (active) networks"""
    try:
        whitelisted = request.args.get('whitelisted')
        recent_only = request.args.get('recent_only', 'true').lower() == 'true'
        
        if whitelisted is not None:
            whitelisted = whitelisted.lower() == 'true'
        
        networks = db.get_networks(whitelisted=whitelisted)
        
        # Filter to only show networks seen in the last 5 minutes
        if recent_only:
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(minutes=5)
            
            filtered_networks = []
            for n in networks:
                try:
                    # SQLite stores as: '2025-11-30 19:27:21'
                    last_seen = datetime.strptime(n['last_seen'], '%Y-%m-%d %H:%M:%S')
                    
                    if last_seen > cutoff_time:
                        filtered_networks.append(n)
                    else:
                        logger.debug(f"Filtering out {n['ssid']} - last seen {n['last_seen']}")
                except Exception as e:
                    logger.error(f"Error parsing date for {n.get('ssid', 'unknown')}: {e} - Value: {n.get('last_seen')}")
                    # Include network if date parsing fails
                    filtered_networks.append(n)
            
            logger.info(f"Filtered networks: {len(filtered_networks)}/{len(networks)} networks within 5 minutes")
            networks = filtered_networks
        
        return jsonify({
            'success': True,
            'networks': networks
        })
    except Exception as e:
        logger.error(f"Get networks error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/networks/<bssid>/whitelist', methods=['POST'])
def set_whitelist(bssid):
    """Set network whitelist status"""
    try:
        data = request.json
        whitelisted = data.get('whitelisted', False)
        
        db.set_whitelist(bssid, whitelisted)
        
        return jsonify({
            'success': True,
            'message': f"Network {'whitelisted' if whitelisted else 'removed from whitelist'}"
        })
    except Exception as e:
        logger.error(f"Set whitelist error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/handshakes')
def get_handshakes():
    """Get captured handshakes"""
    try:
        status = request.args.get('status')
        
        if status == 'pending':
            handshakes = db.get_pending_handshakes()
        else:
            # Get all handshakes
            conn = db.connect()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM handshakes ORDER BY capture_date DESC')
            handshakes = [dict(row) for row in cursor.fetchall()]
            conn.close()
        
        return jsonify({
            'success': True,
            'handshakes': handshakes
        })
    except Exception as e:
        logger.error(f"Get handshakes error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/passwords')
def get_passwords():
    """Get cracked passwords"""
    try:
        passwords = db.get_cracked_passwords()
        
        return jsonify({
            'success': True,
            'passwords': passwords
        })
    except Exception as e:
        logger.error(f"Get passwords error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scans')
def get_scans():
    """Get enumeration scans"""
    try:
        network_id = request.args.get('network_id', type=int)
        
        scans = db.get_scans(network_id=network_id)
        
        return jsonify({
            'success': True,
            'scans': scans
        })
    except Exception as e:
        logger.error(f"Get scans error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vulnerabilities')
def get_vulnerabilities():
    """Get discovered vulnerabilities"""
    try:
        scan_id = request.args.get('scan_id', type=int)
        severity = request.args.get('severity')
        
        vulnerabilities = db.get_vulnerabilities(scan_id=scan_id, severity=severity)
        
        return jsonify({
            'success': True,
            'vulnerabilities': vulnerabilities
        })
    except Exception as e:
        logger.error(f"Get vulnerabilities error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export', methods=['POST'])
def export_data():
    """Export database to JSON"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_path = f"/tmp/pendonn_export_{timestamp}.json"
        
        db.export_data(export_path)
        
        return send_file(
            export_path,
            as_attachment=True,
            download_name=f"pendonn_export_{timestamp}.json",
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/database/reset', methods=['POST'])
def reset_database():
    """Reset database (with backup)"""
    try:
        data = request.json
        keep_backup = data.get('keep_backup', True)
        
        db.reset_database(keep_backup=keep_backup)
        
        return jsonify({
            'success': True,
            'message': 'Database reset successfully'
        })
    except Exception as e:
        logger.error(f"Reset database error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config')
def get_config():
    """Get system configuration (sanitized)"""
    try:
        # Return sanitized config (hide secret key)
        safe_config = config.copy()
        if 'web' in safe_config:
            safe_config['web']['secret_key'] = '***HIDDEN***'
        
        return jsonify({
            'success': True,
            'config': safe_config
        })
    except Exception as e:
        logger.error(f"Get config error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['PUT'])
def update_config():
    """Update system configuration"""
    try:
        data = request.json
        
        # Update config file
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Reload config
        global config
        config = data
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated. Restart services for changes to take effect.'
        })
    except Exception as e:
        logger.error(f"Update config error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/service/<action>', methods=['POST'])
def control_service(action):
    """Control system service (start/stop/restart)"""
    try:
        import subprocess
        
        if action not in ['start', 'stop', 'restart']:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
        result = subprocess.run(
            ['systemctl', action, 'pendonn'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': f'Service {action}ed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 500
    
    except Exception as e:
        logger.error(f"Service control error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/whitelist', methods=['GET'])
def get_whitelist():
    """Get whitelist"""
    try:
        whitelist = config['whitelist']['ssids']
        return jsonify({
            'success': True,
            'whitelist': whitelist
        })
    except Exception as e:
        logger.error(f"Get whitelist error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/whitelist', methods=['POST'])
def add_to_whitelist():
    """Add SSID to whitelist"""
    try:
        data = request.json
        ssid = data.get('ssid')
        
        if not ssid:
            return jsonify({'success': False, 'error': 'SSID required'}), 400
        
        if ssid not in config['whitelist']['ssids']:
            config['whitelist']['ssids'].append(ssid)
            
            # Save config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'{ssid} added to whitelist'
        })
    except Exception as e:
        logger.error(f"Add to whitelist error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/whitelist/<ssid>', methods=['DELETE'])
def remove_from_whitelist(ssid):
    """Remove SSID from whitelist"""
    try:
        if ssid in config['whitelist']['ssids']:
            config['whitelist']['ssids'].remove(ssid)
            
            # Save config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'{ssid} removed from whitelist'
        })
    except Exception as e:
        logger.error(f"Remove from whitelist error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/stream')
def stream_logs():
    """Stream systemd journal logs using Server-Sent Events"""
    def generate():
        lines = request.args.get('lines', 100, type=int)
        
        # Start journalctl process with follow
        process = subprocess.Popen(
            ['journalctl', '-u', 'pendonn', '-f', '-n', str(lines), '--no-pager'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    yield f"data: {line.rstrip()}\n\n"
        except GeneratorExit:
            process.terminate()
            process.wait()
    
    return Response(stream_with_context(generate()), 
                   mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'X-Accel-Buffering': 'no'
                   })


@app.route('/api/logs')
def get_logs():
    """Get recent logs (non-streaming)"""
    try:
        lines = request.args.get('lines', 100, type=int)
        
        result = subprocess.run(
            ['journalctl', '-u', 'pendonn', '-n', str(lines), '--no-pager'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'logs': result.stdout.split('\n')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 500
    except Exception as e:
        logger.error(f"Get logs error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    host = config['web']['host']
    port = config['web']['port']
    
    logger.info(f"Starting PenDonn Web Interface on {host}:{port}")
    app.run(host=host, port=port, debug=False)
