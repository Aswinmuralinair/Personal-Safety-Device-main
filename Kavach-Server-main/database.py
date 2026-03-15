from flask_sqlalchemy import SQLAlchemy
import datetime

DB = SQLAlchemy()

class Alert(DB.Model):
    __tablename__ = 'alerts'

    id = DB.Column(DB.Integer, primary_key=True)
    timestamp = DB.Column(DB.DateTime, default=datetime.datetime.now(datetime.UTC))
    device_id = DB.Column(DB.String(64), nullable=False)
    
    call_placed_status = DB.Column(DB.Boolean, default=False)
    guardian_sms_status = DB.Column(DB.Boolean, default=False)
    location_sms_status = DB.Column(DB.Boolean, default=False)
    
    gps_location = DB.Column(DB.String(255), nullable=True)
    
    # --- NEW COLUMN ---
    battery_percentage = DB.Column(DB.String(10), nullable=True)
    # ------------------
    
    uploaded_files = DB.Column(DB.String(1024), nullable=True)

    def __repr__(self):
        return f"<Alert(id={self.id}, device='{self.device_id}')>"