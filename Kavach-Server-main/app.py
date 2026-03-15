from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from database import DB, Alert
from utils import save_file_safe
import sys # Added to flush output immediately
import json
import base64
from crypto_utils import chacha_decrypt_text


app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kavach.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

DB.init_app(app)

UPLOAD_DIR = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route('/api/alerts', methods=['POST'])
def alerts():
    try:
        files = request.files
        encrypted_payload_b64 = request.form.get('encrypted_payload')

        if not encrypted_payload_b64:
            return jsonify({'status': 'error', 'message': 'Missing encrypted payload'}), 400

        # Decode base64 → bytes
        encrypted_payload = base64.b64decode(encrypted_payload_b64)

        # --- [ENCRYPTION CHECK] START ---
        print("\n" + "*"*50)
        print(" [SECURITY CHECK] RAW ENCRYPTED PAYLOAD (First 50 bytes):")
        print(f" {encrypted_payload[:50]}") 
        print("*"*50 + "\n")
        # --- [ENCRYPTION CHECK] END ---

        # Decrypt
        decrypted_json = chacha_decrypt_text(encrypted_payload)

        # Convert back to dict
        data = json.loads(decrypted_json)

        
        # --- [SERVER DEBUG LOG] START ---
        print("\n" + "="*50)
        print(" [SERVER LOG] RECEIVED NEW POST REQUEST")
        print("="*50)
        print(f" Device ID:      {data.get('device_id')}")
        print(f" Timestamp:      {data.get('timestamp')}")
        
        rec_loc = data.get('location') or data.get('gps_location')
        print(f" GPS Location:   {rec_loc}") 
        
        # --- NEW DEBUG LINE ---
        print(f" Battery %:      {data.get('battery_percentage')}")
        
        print(f" Call Status:    {data.get('call_placed_status')}")
        print(f" SMS Status:     {data.get('guardian_sms_status')}")
        print(f" Files Received: {list(files.keys())}")
        print("="*50 + "\n")
        sys.stdout.flush() # Force print to terminal immediately
        # --- [SERVER DEBUG LOG] END ---

        device_id = data.get('device_id')
        if not device_id:
            print(" [ERROR] device_id missing")
            return jsonify({'status':'error', 'message':'device_id is required'}), 400

        saved_filenames = []
        
        for name in files:
            f = files[name]
            path = save_file_safe(f, UPLOAD_DIR)
            if path:
                print(f" [SERVER LOG] Saved file: {os.path.basename(path)}")
                saved_filenames.append(os.path.basename(path))
        
        location_data = data.get('location')
        if not location_data:
            location_data = data.get('gps_location')
            
        # --- NEW: Get battery data ---
        battery_data = data.get('battery_percentage')

        new_alert = Alert(
            device_id=device_id,
            # Wrap in str() to handle both boolean (True) and string ("True") data safely
            call_placed_status=str(data.get('call_placed_status', 'false')).lower() == 'true',
            guardian_sms_status=str(data.get('guardian_sms_status', 'false')).lower() == 'true',
            location_sms_status=str(data.get('location_sms_status', 'false')).lower() == 'true',
            gps_location=location_data,
            battery_percentage=data.get('battery_percentage'),
            uploaded_files=','.join(saved_filenames)
        )
        
        DB.session.add(new_alert)
        DB.session.commit()
        
        print(f" [SERVER LOG] Alert saved to DB with ID: {new_alert.id}")
        return jsonify({'status':'ok', 'saved': saved_filenames, 'alert_id': new_alert.id}), 201

    except Exception as e:
        print(f" [SERVER ERROR] {str(e)}")
        DB.session.rollback()
        return jsonify({'status':'error', 'message': str(e)}), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == '__main__':
    with app.app_context():
        # This will see the new column and add it
        DB.create_all() 
    app.run(host='0.0.0.0', port=8080, debug=True)