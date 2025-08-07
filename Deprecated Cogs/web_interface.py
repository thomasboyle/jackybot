from flask import Flask, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json

db = SQLAlchemy()

class CommandUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    command = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bot_usage.db'
    db.init_app(app)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/usage_data')
    def usage_data():
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        usage = CommandUsage.query.filter(CommandUsage.timestamp.between(start_date, end_date)).all()
        
        data = {}
        for entry in usage:
            date = entry.timestamp.strftime('%Y-%m-%d')
            if date not in data:
                data[date] = {}
            if entry.command not in data[date]:
                data[date][entry.command] = 0
            data[date][entry.command] += 1
        
        return jsonify(data)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)