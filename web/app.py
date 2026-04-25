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
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, send_file, Response,
    stream_with_context,
)
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import ensure_persistent_secret, load_config
from core.database import Database
from core.pdf_report import PDFReport

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load configuration (config.json + optional config.json.local overlay).
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
config = load_config(config_path)

# Resolve Flask secret_key. Empty / placeholder values trigger generation
# of a fresh secret persisted to config.json.local (chmod 0600). Subsequent
# starts read it back from .local — sessions survive restarts.
app.config['SECRET_KEY'] = ensure_persistent_secret(config, config_path)

# Initialize database
db = Database(config['database']['path'])


# ---------------------------------------------------------------------------
# Basic Auth
#
# Off by default for backward compat (loopback-only is the safe default).
# The bind-safety check below refuses to start with host=0.0.0.0 unless
# auth is enabled. Configure via config.json.local:
#
#     "web": {
#       "basic_auth": {
#         "enabled": true,
#         "username": "linus",
#         "password_hash": "scrypt:..." or "pbkdf2:..."
#       }
#     }
#
# Generate a hash with:  python web/app.py --hash-password
# Falls back to checking a plaintext "password" field with a deprecation
# warning, so existing operators don't get locked out by the upgrade.
# ---------------------------------------------------------------------------

_auth_cfg = (config.get('web', {}) or {}).get('basic_auth', {}) or {}
_AUTH_ENABLED = bool(_auth_cfg.get('enabled', False))
_AUTH_USER = _auth_cfg.get('username') or ''
_AUTH_HASH = _auth_cfg.get('password_hash') or ''
_AUTH_PLAINTEXT = _auth_cfg.get('password') or ''
if _AUTH_ENABLED and not _AUTH_HASH and _AUTH_PLAINTEXT:
    logger.warning(
        "web.basic_auth.password is set in PLAINTEXT — generate a hash with "
        "`python web/app.py --hash-password` and store it as password_hash "
        "in config.json.local instead. Plaintext support will be removed."
    )

# Routes that must NEVER require auth (operator can lock themselves out
# of /api/config otherwise; captive-portal endpoints serve evil-twin
# victims who obviously can't authenticate).
_AUTH_EXEMPT_PREFIXES = ('/captive/', '/static/')
_AUTH_EXEMPT_PATHS = {'/health', '/favicon.ico'}


def _check_basic_auth_credentials(username: str, password: str) -> bool:
    """Constant-time-ish credential check. Returns True iff valid."""
    if not _AUTH_ENABLED:
        return True
    if not username or username != _AUTH_USER:
        return False
    if _AUTH_HASH:
        try:
            return check_password_hash(_AUTH_HASH, password)
        except (ValueError, TypeError) as e:
            logger.error("Bad password_hash format: %s", e)
            return False
    if _AUTH_PLAINTEXT:
        # Constant-time comparison via secrets.compare_digest
        import secrets as _s
        return _s.compare_digest(password, _AUTH_PLAINTEXT)
    return False


@app.before_request
def _enforce_basic_auth():
    if not _AUTH_ENABLED:
        return None
    path = request.path or ''
    if path in _AUTH_EXEMPT_PATHS:
        return None
    if any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return None
    auth = request.authorization
    if auth and _check_basic_auth_credentials(auth.username or '', auth.password or ''):
        return None
    return Response(
        'Authentication required.\n', 401,
        {'WWW-Authenticate': 'Basic realm="PenDonn"'},
    )


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
        
        # Filter to only show networks seen in the last 30 minutes (more reasonable)
        if recent_only:
            from datetime import timedelta, timezone
            # Database stores UTC timestamps, so compare in UTC
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)
            cutoff_time = cutoff_time.replace(tzinfo=None)  # Remove timezone for comparison
            
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


@app.route('/api/export/pdf', methods=['GET'])
def export_pdf():
    """Export scan report as PDF"""
    try:
        scan_id = request.args.get('scan_id')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Set output path
        pdf_path = f"/tmp/pendonn_report_{timestamp}.pdf"
        
        logger.info(f"Starting PDF generation: {pdf_path}")
        
        # Generate PDF report
        report = PDFReport(db, output_path=pdf_path)
        
        logger.info("PDFReport object created")
        
        if scan_id:
            # Export specific scan - include only that scan's data
            # For now, generate full report (can be enhanced later to filter by scan_id)
            logger.info(f"Generating report for scan_id: {scan_id}")
            report.generate_report(include_sections=[
                'summary', 'scans', 'vulnerabilities', 'recommendations'
            ])
            filename = f"pendonn_scan_{scan_id}_{timestamp}.pdf"
        else:
            # Export full report (all scans and vulnerabilities)
            logger.info("Generating full report")
            report.generate_report()
            filename = f"pendonn_report_{timestamp}.pdf"
        
        logger.info(f"PDF generated successfully: {pdf_path}")
        
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        logger.error(f"PDF export error: {e}")
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_details}")
        
        # Write to separate error file for debugging
        with open('/tmp/pdf_error.log', 'w') as f:
            f.write(f"Error: {e}\n\n")
            f.write(error_details)
        
        return jsonify({'success': False, 'error': str(e), 'details': error_details}), 500


@app.route('/api/database/reset', methods=['POST'])
def reset_database():
    """Reset database (with backup and file cleanup)"""
    try:
        data = request.json
        keep_backup = data.get('keep_backup', True)
        clean_files = data.get('clean_files', True)  # Default to cleaning files
        
        db.reset_database(keep_backup=keep_backup, clean_files=clean_files)
        
        return jsonify({
            'success': True,
            'message': 'Database reset successfully. Files cleaned.' if clean_files else 'Database reset successfully.'
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


def _hash_password_cli() -> int:
    """Interactive helper: prompt for a password and print a werkzeug hash.

    Operator copies the printed line into config.json.local under
    web.basic_auth.password_hash. We never echo the password and never
    write the hash to disk on behalf of the operator — they paste it
    explicitly so they're aware of where the secret lives.
    """
    import getpass
    pw = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm:  ")
    if pw != pw2:
        print("Passwords don't match.", file=sys.stderr)
        return 1
    if len(pw) < 8:
        print("Refusing: password must be at least 8 characters.", file=sys.stderr)
        return 1
    print(generate_password_hash(pw))
    print(
        "\nAdd to config/config.json.local:\n"
        '  "web": { "basic_auth": { "enabled": true, '
        '"username": "<your-username>", "password_hash": "<the line above>" } }',
        file=sys.stderr,
    )
    return 0


def _refuse_unauth_lan_exposure(host: str) -> None:
    """Exit if host=0.0.0.0 (LAN-exposed) and basic_auth is disabled.

    Defends against the most common foot-gun: operator flips host to
    0.0.0.0 to hit the dashboard from their laptop, forgets to enable auth,
    and now /api/database/reset and /api/service/stop are reachable from
    every device on the network. Loopback-only is fine without auth.
    """
    if host in ('127.0.0.1', 'localhost', '::1'):
        return
    if _AUTH_ENABLED:
        logger.warning(
            "Web server bound to %s — make sure basic_auth credentials "
            "are strong; CSRF protection is NOT enabled in this UI yet.",
            host,
        )
        return
    logger.error("=" * 60)
    logger.error("REFUSING TO START: web.host=%s but basic_auth is disabled.", host)
    logger.error("Either:")
    logger.error("  1) set web.host to 127.0.0.1 (loopback only), OR")
    logger.error("  2) configure web.basic_auth.{enabled,username,password_hash}")
    logger.error("     in config.json.local — generate a hash with:")
    logger.error("         python web/app.py --hash-password")
    logger.error("=" * 60)
    sys.exit(2)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--hash-password':
        sys.exit(_hash_password_cli())

    host = config['web']['host']
    port = config['web']['port']
    _refuse_unauth_lan_exposure(host)

    auth_state = "enabled" if _AUTH_ENABLED else "DISABLED (loopback-only ok)"
    logger.info(
        "Starting PenDonn Web Interface on %s:%s (basic_auth: %s)",
        host, port, auth_state,
    )
    app.run(host=host, port=port, debug=False)
