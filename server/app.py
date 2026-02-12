from flask import Flask, request, jsonify, send_from_directory, render_template_string
import datetime
import json
import base64

app = Flask(__name__)

# Store the received data (in memory)
received_data = []
processed_health_data = []
critical_alerts = []  # New: Store only critical alerts

def decode_data(enc_data):
    """Decode Base64 data from ESP8266"""
    try:
        # Try to decode as base64
        decoded_bytes = base64.b64decode(enc_data)
        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
        return decoded_str.strip()
    except Exception as e:
        print(f"❌ Base64 decoding error: {e}")
        # If base64 fails, maybe it's plain text
        return enc_data.strip()

def is_critical_condition(heart_rate, fall_detected):
    """Check if condition is critical (both fall AND high heart rate)"""
    return fall_detected == 1 and heart_rate > 100

@app.route('/test', methods=['GET'])
def test():
    return jsonify({
        "status": "Server is working! (Critical Alerts Only Mode)",
        "timestamp": datetime.datetime.now().isoformat(),
        "server_ip": request.host,
        "total_messages": len(received_data),
        "health_data": len(processed_health_data),
        "critical_alerts": len(critical_alerts)
    })

@app.route('/update', methods=['POST'])
def update():
    current_time = datetime.datetime.now()
    
    print(f"\n=== DATA RECEIVED ===")
    print(f"Time: {current_time}")
    print(f"Headers: {dict(request.headers)}")
    
    # Get raw data
    raw_data = request.data.decode('utf-8', errors='ignore')
    print(f"Raw Data: {raw_data}")
    print(f"Raw Data Length: {len(raw_data)}")
    
    # Store raw data info
    data_info = {
        "timestamp": current_time.isoformat(),
        "headers": dict(request.headers),
        "raw_data": raw_data,
        "data_length": len(request.data),
        "content_type": request.headers.get('Content-Type', 'unknown')
    }
    
    # Check if it's Basic Auth from ESP8266
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            auth_decoded = base64.b64decode(auth_header.split(" ")[1]).decode()
            username, password = auth_decoded.split(":", 1)
            data_info["auth_user"] = username
            print(f"👤 Auth User: {username}")
        except:
            data_info["auth_user"] = "decode_failed"
    
    # Try to decode the data
    decoded_json = decode_data(raw_data)
    
    if decoded_json:
        print(f"✅ Decoded Data: {decoded_json}")
        data_info["decoded"] = decoded_json
        
        # Try to parse as JSON
        try:
            health_data = json.loads(decoded_json)
            heart_rate = health_data.get('heart_rate', 0)
            fall_detected = health_data.get('fall', 0)
            patient_id = health_data.get('patient_id', 'Unknown')
            
            print(f"💓 Heart Rate: {heart_rate} BPM")
            print(f"🚨 Fall Detected: {'Yes' if fall_detected else 'No'}")
            print(f"👤 Patient ID: {patient_id}")
            
            # Store all health data (for logging purposes)
            processed_entry = {
                'timestamp': current_time.isoformat(),
                'heart_rate': heart_rate,
                'fall': fall_detected,
                'patient_id': patient_id,
                'data': decoded_json,
                'is_critical': is_critical_condition(heart_rate, fall_detected)
            }
            
            processed_health_data.append(processed_entry)
            
            # Check if this is a CRITICAL condition (Fall + High HR)
            if is_critical_condition(heart_rate, fall_detected):
                print(f"🚨🚨🚨 CRITICAL ALERT: Fall + High HR ({heart_rate} BPM) 🚨🚨🚨")
                
                critical_alert = {
                    'timestamp': current_time.isoformat(),
                    'heart_rate': heart_rate,
                    'fall': fall_detected,
                    'patient_id': patient_id,
                    'alert_type': 'CRITICAL',
                    'severity': 'HIGH',
                    'message': f'Fall detected with elevated heart rate ({heart_rate} BPM)'
                }
                
                critical_alerts.append(critical_alert)
                
                # Keep only last 50 critical alerts
                if len(critical_alerts) > 50:
                    critical_alerts.pop(0)
            else:
                print(f"ℹ️ Normal condition - not critical (Fall: {fall_detected}, HR: {heart_rate})")
            
            # Keep only last 100 health readings
            if len(processed_health_data) > 100:
                processed_health_data.pop(0)
                
            data_info["parsed_heart_rate"] = heart_rate
            data_info["parsed_fall"] = fall_detected
            data_info["parsed_patient_id"] = patient_id
            data_info["parsing_success"] = True
            data_info["is_critical"] = is_critical_condition(heart_rate, fall_detected)
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            print(f"❌ Failed to parse: '{decoded_json}'")
            data_info["json_error"] = str(e)
            data_info["parsing_success"] = False
    else:
        print("❌ Failed to decode data")
        data_info["decoding_failed"] = True
        data_info["parsing_success"] = False
    
    # Store raw data
    received_data.append(data_info)
    
    # Keep only last 50 raw messages
    if len(received_data) > 50:
        received_data.pop(0)
    
    print(f"📊 Total stored messages: {len(received_data)}")
    print(f"💊 Total health data: {len(processed_health_data)}")
    print(f"🚨 Critical alerts: {len(critical_alerts)}")
    print(f"===================\n")
    
    return jsonify({
        "status": "received", 
        "message_count": len(received_data),
        "health_data_count": len(processed_health_data),
        "critical_alerts_count": len(critical_alerts),
        "decoding_successful": decoded_json is not None and data_info.get("parsing_success", False),
        "is_critical": data_info.get("is_critical", False)
    }), 200

@app.route('/data')
def get_data():
    """API endpoint to get ALL health data for debugging"""
    print(f"📊 All data requested - returning {len(processed_health_data)} records")
    return jsonify(processed_health_data)

@app.route('/critical-alerts')
def get_critical_alerts():
    """API endpoint to get ONLY critical alerts for UI"""
    print(f"🚨 Critical alerts requested - returning {len(critical_alerts)} critical alerts")
    return jsonify(critical_alerts)

@app.route('/raw-data')
def get_raw_data():
    """API endpoint to get raw received data"""
    return jsonify(received_data)

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files (your HTML dashboards)"""
    return send_from_directory('static', filename)

@app.route('/medical')
def medical_dashboard():
    """Medical Dashboard route - redirect to static file"""
    return send_from_directory('static', 'medical_dashboard.html')

@app.route('/')
def dashboard():
    """Main dashboard route - ONLY shows critical alerts"""
    dashboard_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ESP8266 Critical Health Alerts</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .header {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 20px;
                text-align: center;
            }
            
            .header h1 {
                color: #dc3545;
                margin-bottom: 10px;
            }
            
            .critical-notice {
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                border: 1px solid #f5c6cb;
                font-weight: bold;
            }
            
            .nav-links {
                margin-top: 15px;
                display: flex;
                gap: 10px;
                justify-content: center;
                flex-wrap: wrap;
            }
            
            .nav-link {
                background: #dc3545;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                transition: background 0.3s;
            }
            
            .nav-link:hover {
                background: #c82333;
                text-decoration: none;
                color: white;
            }
            
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                text-align: center;
            }
            
            .stat-number {
                font-size: 2em;
                font-weight: bold;
                color: #dc3545;
            }
            
            .stat-label {
                color: #666;
                margin-top: 5px;
            }
            
            .status-indicator {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                display: inline-block;
                margin-right: 8px;
                animation: pulse 1s infinite;
            }
            
            .status-critical { background: #dc3545; }
            .status-normal { background: #28a745; }
            .status-warning { background: #ffc107; }
            
            @keyframes pulse {
                0% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.7; transform: scale(1.1); }
                100% { opacity: 1; transform: scale(1); }
            }
            
            .alerts-section {
                background: white;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                overflow: hidden;
                margin-bottom: 20px;
            }
            
            .section-header {
                background: #dc3545;
                color: white;
                padding: 15px 20px;
                font-weight: bold;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .alerts-content {
                padding: 20px;
                max-height: 500px;
                overflow-y: auto;
            }
            
            .critical-alert {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px;
                margin: 15px 0;
                background: linear-gradient(135deg, #fff5f5 0%, #ffeaea 100%);
                border-radius: 10px;
                border-left: 5px solid #dc3545;
                box-shadow: 0 2px 4px rgba(220, 53, 69, 0.2);
                animation: alertPulse 2s infinite;
            }
            
            @keyframes alertPulse {
                0% { box-shadow: 0 2px 4px rgba(220, 53, 69, 0.2); }
                50% { box-shadow: 0 4px 8px rgba(220, 53, 69, 0.4); }
                100% { box-shadow: 0 2px 4px rgba(220, 53, 69, 0.2); }
            }
            
            .alert-info {
                flex: 1;
            }
            
            .alert-title {
                font-size: 1.3em;
                font-weight: bold;
                color: #dc3545;
                margin-bottom: 8px;
            }
            
            .alert-details {
                font-size: 1.1em;
                color: #333;
                margin-bottom: 5px;
            }
            
            .alert-patient {
                font-size: 0.95em;
                color: #666;
                margin-bottom: 5px;
            }
            
            .alert-timestamp {
                font-size: 0.9em;
                color: #666;
            }
            
            .alert-badge {
                background: #dc3545;
                color: white;
                padding: 8px 15px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 0.95em;
                animation: blink 1s infinite;
            }
            
            @keyframes blink {
                0%, 50% { opacity: 1; }
                51%, 100% { opacity: 0.8; }
            }
            
            .no-alerts {
                text-align: center;
                color: #28a745;
                font-size: 1.2em;
                font-weight: bold;
                padding: 60px 20px;
                background: #d4edda;
                border-radius: 10px;
                border: 2px solid #c3e6cb;
            }
            
            .system-status {
                background: white;
                padding: 15px 20px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 20px;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚨 Critical Health Alert System</h1>
                <p><span id="connectionStatus" class="status-indicator status-normal"></span>Monitoring for critical conditions only</p>
                
                <div class="critical-notice">
                    ⚠️ This system ONLY displays alerts when BOTH fall detection AND high heart rate (>100 BPM) occur together
                </div>
                
                <div class="nav-links">
                    <a href="/static/patient_dashboard.html" class="nav-link">👤 Patient Dashboard</a>
                    <a href="/medical" class="nav-link">👨‍⚕️ Medical Dashboard</a>
                    <a href="/data" class="nav-link">📊 All Data (Debug)</a>
                    <a href="/test" class="nav-link">🔧 Test API</a>
                </div>
            </div>
            
            <div class="system-status">
                <p>System Status: <span id="systemStatus">Monitoring...</span></p>
                <p>Last Update: <span id="lastUpdate">--</span></p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="criticalCount">0</div>
                    <div class="stat-label">Critical Alerts</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="lastCriticalHR">--</div>
                    <div class="stat-label">Last Critical HR</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="monitoringTime">0</div>
                    <div class="stat-label">Minutes Monitoring</div>
                </div>
            </div>
            
            <div class="alerts-section">
                <div class="section-header">
                    <span>🚨</span>
                    <span>CRITICAL ALERTS (Fall + High Heart Rate Only)</span>
                </div>
                <div class="alerts-content" id="criticalAlerts">Loading...</div>
            </div>
        </div>

        <script>
            let startTime = Date.now();
            
            async function fetchCriticalAlerts() {
                try {
                    let response = await fetch('/critical-alerts');
                    let criticalAlerts = await response.json();
                    
                    updateCriticalAlerts(criticalAlerts);
                    updateStats(criticalAlerts);
                    updateSystemStatus();
                    
                } catch (error) {
                    console.error('Error fetching critical alerts:', error);
                    document.getElementById('systemStatus').textContent = 'Connection Error';
                    document.getElementById('connectionStatus').className = 'status-indicator status-warning';
                }
            }
            
            function updateCriticalAlerts(alerts) {
                let container = document.getElementById('criticalAlerts');
                
                if (alerts.length === 0) {
                    container.innerHTML = `
                        <div class="no-alerts">
                            ✅ No Critical Alerts<br>
                            <small>System is monitoring... Critical alerts appear only when fall is detected AND heart rate > 100 BPM</small>
                        </div>
                    `;
                    return;
                }
                
                let html = '';
                // Show most recent alerts first
                for (let i = alerts.length - 1; i >= 0; i--) {
                    let alert = alerts[i];
                    
                    html += `
                        <div class="critical-alert">
                            <div class="alert-info">
                                <div class="alert-title">🚨 CRITICAL EMERGENCY</div>
                                <div class="alert-details">❤️ Heart Rate: ${alert.heart_rate} BPM + 🤕 Fall Detected</div>
                                <div class="alert-patient">👤 Patient: ${alert.patient_id}</div>
                                <div class="alert-timestamp">⏰ ${new Date(alert.timestamp).toLocaleString()}</div>
                            </div>
                            <div class="alert-badge">EMERGENCY</div>
                        </div>
                    `;
                }
                
                container.innerHTML = html;
            }
            
            function updateStats(criticalAlerts) {
                document.getElementById('criticalCount').textContent = criticalAlerts.length;
                
                if (criticalAlerts.length > 0) {
                    let lastAlert = criticalAlerts[criticalAlerts.length - 1];
                    document.getElementById('lastCriticalHR').textContent = lastAlert.heart_rate + ' bpm';
                    document.getElementById('connectionStatus').className = 'status-indicator status-critical';
                } else {
                    document.getElementById('lastCriticalHR').textContent = '--';
                    document.getElementById('connectionStatus').className = 'status-indicator status-normal';
                }
                
                let monitoringMinutes = Math.floor((Date.now() - startTime) / 60000);
                document.getElementById('monitoringTime').textContent = monitoringMinutes;
            }
            
            function updateSystemStatus() {
                document.getElementById('systemStatus').textContent = 'Active - Monitoring for Critical Conditions';
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
            }
            
            // Initial load and auto-refresh every 3 seconds
            document.addEventListener('DOMContentLoaded', function() {
                console.log('Critical Alert System Started');
                fetchCriticalAlerts();
                setInterval(fetchCriticalAlerts, 3000);
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(dashboard_html)

if __name__ == '__main__':
    print("🚨 Starting CRITICAL ALERTS ONLY health monitor server...")
    print("⚠️  This version ONLY shows alerts when BOTH fall AND high heart rate (>100) occur")
    print("📡 Test URL: http://0.0.0.0:5000/test")
    print("🚨 Critical Alerts Dashboard: http://0.0.0.0:5000/")
    print("📊 All Data (Debug): http://0.0.0.0:5000/data")
    print("🚨 Critical Alerts API: http://0.0.0.0:5000/critical-alerts")
    
    app.run(host='0.0.0.0', port=5000, debug=True)