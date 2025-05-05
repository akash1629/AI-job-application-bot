import os
import time
import uuid
from datetime import datetime

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# Parsing
import spacy
from pdfminer.high_level import extract_text

# Automation & Scheduling
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from apscheduler.schedulers.background import BackgroundScheduler


def create_app(config_overrides=None):
    app = Flask(__name__)

    # Configuration
    default_config = {
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///job_bot.db',
        'SECRET_KEY': os.getenv('SECRET_KEY', 'change_this_secret'),
        'UPLOAD_FOLDER': os.getenv('UPLOAD_FOLDER', 'uploads'),
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB limit
        'SCHEDULER_API_ENABLED': True
    }
    app.config.update(default_config)
    if config_overrides:
        app.config.update(config_overrides)

    # Extensions
    db.init_app(app)
    scheduler.init_app(app)
    scheduler.start()

    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize NLP
    nlp = spacy.load('en_core_web_sm')

    # Register routes
    register_routes(app, nlp)

    with app.app_context():
        db.create_all()

    return app


# Initialize extensions outside create_app for potential reuse/testing
db = SQLAlchemy()
scheduler = BackgroundScheduler()


# Database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)  # hash length
    location = db.Column(db.String(100))
    experience = db.Column(db.Integer)
    resume_path = db.Column(db.String(255))


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(100))
    apply_link = db.Column(db.String(500))


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50), default='Pending')
    applied_at = db.Column(db.DateTime)


# Helper functions

def parse_resume(file_path, nlp):
    text = extract_text(file_path)
    doc = nlp(text)

    parsed = {'name': None, 'email': None, 'skills': []}
    # Extract entities
    for ent in doc.ents:
        if ent.label_ == 'PERSON' and not parsed['name']:
            parsed['name'] = ent.text
        elif ent.label_ == 'EMAIL':
            parsed['email'] = ent.text

    # Skill matching
    tokens = {t.text.lower() for t in doc if not t.is_stop}
    skills = [s for s in ['python', 'sql', 'tableau', 'power bi', 'machine learning', 'excel'] if s in tokens]
    parsed['skills'] = skills
    return parsed


def run_selenium_apply(apply_link, resume_path):
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(apply_link)
        time.sleep(2)
        # implement site-specific logic with robust element checks
    finally:
        driver.quit()


def schedule_application(user_id, job_id, run_time):
    job_id_str = f"apply_{user_id}_{job_id}"
    scheduler.add_job(execute_application, 'date', run_date=run_time,
                      args=[user_id, job_id], id=job_id_str, replace_existing=True)


def execute_application(user_id, job_id):
    user = User.query.get(user_id)
    job = Job.query.get(job_id)
    if not (user and job):
        return
    run_selenium_apply(job.apply_link, user.resume_path)
    application = Application.query.filter_by(user_id=user_id, job_id=job_id).first()
    if application:
        application.status = 'Applied'
        application.applied_at = datetime.utcnow()
    else:
        application = Application(user_id=user_id, job_id=job_id,
                                  status='Applied', applied_at=datetime.utcnow())
        db.session.add(application)
    db.session.commit()


def scrape_jobs(keyword, location):
    # Placeholder for proper API integration
    return [
        {'title': 'Data Scientist', 'company': 'ABC Corp', 'location': location,
         'apply_link': 'https://example.com/apply/123'}
    ]


def register_routes(app, nlp):
    @app.route('/register', methods=['POST'])
    def register():
        data = request.json or {}
        email = data.get('email'); password = data.get('password')
        if not email or not password:
            return jsonify(error='Email and password required'), 400
        if User.query.filter_by(email=email).first():
            return jsonify(error='Email exists'), 400
        # TODO: hash password before storing
        user = User(email=email, password=password,
                    location=data.get('location'), experience=data.get('experience'))
        db.session.add(user); db.session.commit()
        return jsonify(message='Registered'), 201

    @app.route('/login', methods=['POST'])
    def login():
        data = request.json or {}
        user = User.query.filter_by(email=data.get('email')).first()
        if user and user.password == data.get('password'):
            return jsonify(message='Login successful', user_id=user.id)
        return jsonify(error='Invalid credentials'), 401

    @app.route('/upload_resume', methods=['POST'])
    def upload_resume_route():
        user_id = request.form.get('user_id')
        user = User.query.get(user_id) or None
        if not user:
            return jsonify(error='Invalid user ID'), 400
        file = request.files.get('resume')
        if not file:
            return jsonify(error='No file uploaded'), 400
        filename = secure_filename(file.filename)
        unique = f"{uuid.uuid4()}_{filename}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], unique)
        file.save(path)
        parsed = parse_resume(path, nlp)
        user.resume_path = path; db.session.commit()
        return jsonify(message='Uploaded', parsed_data=parsed)

    @app.route('/search_jobs', methods=['GET'])
    def search_jobs_route():
        user = User.query.get(request.args.get('user_id'))
        if not user:
            return jsonify(error='Invalid user ID'), 400
        jobs = scrape_jobs(request.args.get('keyword', ''), user.location)
        response = []
        for j in jobs:
            job = Job.query.filter_by(**j).first()
            if not job:
                job = Job(**j); db.session.add(job); db.session.commit()
            response.append({
                'job_id': job.id, 'title': job.title,
                'company': job.company, 'location': job.location,
                'apply_link': job.apply_link
            })
        return jsonify(jobs=response)

    @app.route('/apply_job', methods=['POST'])
    def apply_job_route():
        data = request.json or {}
        user = User.query.get(data.get('user_id')); job = Job.query.get(data.get('job_id'))
        if not (user and job):
            return jsonify(error='Invalid IDs'), 400
        if Application.query.filter_by(user_id=user.id, job_id=job.id).first():
            return jsonify(error='Already applied'), 400
        app_record = Application(user_id=user.id, job_id=job.id)
        db.session.add(app_record); db.session.commit()
        schedule_time = data.get('schedule_time')
        if schedule_time:
            try:
                dt = datetime.strptime(schedule_time, '%Y-%m-%d %H:%M:%S')
                schedule_application(user.id, job.id, dt)
                return jsonify(message=f'Scheduled at {schedule_time}')
            except ValueError:
                return jsonify(error='Invalid datetime'), 400
        execute_application(user.id, job.id)
        return jsonify(message='Applied immediately')

    @app.route('/application_status', methods=['GET'])
    def application_status_route():
        user = User.query.get(request.args.get('user_id'))
        if not user:
            return jsonify(error='Invalid user ID'), 400
        apps = Application.query.filter_by(user_id=user.id).all()
        result = []
        for a in apps:
            job = Job.query.get(a.job_id)
            result.append({
                'application_id': a.id,
                'job_title': job.title,
                'company': job.company,
                'status': a.status,
                'applied_at': a.applied_at.isoformat() if a.applied_at else None
            })
        return jsonify(applications=result)


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
