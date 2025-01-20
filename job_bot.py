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

# ============ FLASK SETUP ============

app = Flask(__name__)

# Use SQLite for demo; in production, switch to PostgreSQL or another robust DB.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///job_bot.db'
app.config['SECRET_KEY'] = 'some_random_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)

# Initialize spaCy for resume parsing
nlp = spacy.load('en_core_web_sm')

# Create 'uploads' directory if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


# ============ DATABASE MODELS ============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(100), nullable=True)
    experience = db.Column(db.Integer, nullable=True)
    resume_path = db.Column(db.String(255), nullable=True)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(100), nullable=True)
    apply_link = db.Column(db.String(500), nullable=True)
    # Additional fields as you like


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50), default='Pending')
    applied_at = db.Column(db.DateTime, default=None, nullable=True)


db.create_all()

# ============ SCHEDULER SETUP ============

scheduler = BackgroundScheduler()
scheduler.start()


# ============ HELPER FUNCTIONS ============

def parse_resume(file_path):
    """
    Parse text from the uploaded resume using PDFMiner and spaCy
    to extract potential name, email, phone, etc.
    """
    text = extract_text(file_path)
    doc = nlp(text)

    parsed_data = {
        'name': '',
        'email': '',
        'phone': '',
        'skills': []
    }

    for ent in doc.ents:
        if ent.label_ == 'PERSON' and not parsed_data['name']:
            parsed_data['name'] = ent.text
        elif ent.label_ == 'EMAIL':
            parsed_data['email'] = ent.text
        # For phone, spaCy might not always detect automatically.
        # You might want a custom regex or pattern matching:
        # elif ent.label_ == 'PHONE':
        #     parsed_data['phone'] = ent.text

    # Rudimentary skill detection by checking nouns or known skill words
    # In production, consider a better approach or a custom model
    tokens = [token.text.lower() for token in doc if not token.is_stop]
    common_skills = ["python", "sql", "tableau", "power bi", "machine learning", "excel"]
    matched_skills = [skill for skill in common_skills if skill in " ".join(tokens)]
    parsed_data['skills'] = matched_skills

    return parsed_data


def scrape_jobs(keyword, location):
    """
    This function simulates a job search.
    Replace with actual calls to a job board API (Indeed, LinkedIn, etc.)
    or a Selenium-based scraping approach.
    """
    # For demonstration, let's pretend these are fetched from an API
    # You would integrate with official APIs or carefully handle scraping
    # (while respecting the site’s TOS).
    dummy_jobs = [
        {
            'title': 'Data Scientist',
            'company': 'ABC Corp',
            'location': location,
            'apply_link': 'https://www.example.com/apply/123'
        },
        {
            'title': 'Supply Chain Analyst',
            'company': 'XYZ Inc',
            'location': location,
            'apply_link': 'https://www.example.com/apply/456'
        }
    ]
    # Filter or modify as needed based on 'keyword' or location
    # Return a list of jobs
    return dummy_jobs


def apply_to_job(apply_link, resume_path):
    """
    Example automation to fill out an application form.
    In reality, each site will differ. You may need
    separate scripts or templates for each company/portal.
    """
    # Setup Selenium (headless Chrome)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(apply_link)

        # Example steps (will vary for each site):
        # 1. Find resume upload field
        # 2. Fill in forms
        # 3. Click submit
        # This is just a placeholder, as real forms differ widely.
        time.sleep(2)
        # Suppose there's an input with id="resume-upload"
        # driver.find_element(By.ID, 'resume-upload').send_keys(os.path.abspath(resume_path))
        # time.sleep(1)
        # driver.find_element(By.ID, 'submit-btn').click()

        # Since this is a dummy link, we won't actually do anything.
        print(f"Simulating applying to {apply_link} with resume {resume_path}...")

    except Exception as e:
        print(f"Error applying to {apply_link}: {str(e)}")

    finally:
        driver.quit()


def schedule_job_application(user_id, job_id, run_time):
    """
    Schedule a job to apply at a specific time in the future.
    """
    job_name = f"apply_job_{user_id}_{job_id}"
    scheduler.add_job(
        func=execute_application,
        trigger='date',
        run_date=run_time,
        args=[user_id, job_id],
        id=job_name,
        replace_existing=True
    )
    print(f"Scheduled application job: {job_name} at {run_time}")


def execute_application(user_id, job_id):
    """
    The function that the scheduler calls to actually apply for the job.
    """
    user = User.query.get(user_id)
    job = Job.query.get(job_id)
    if not user or not job:
        print(f"Cannot apply. User or Job not found. user_id={user_id}, job_id={job_id}")
        return

    apply_to_job(job.apply_link, user.resume_path)

    application = Application.query.filter_by(user_id=user_id, job_id=job_id).first()
    if application:
        application.status = "Applied"
        application.applied_at = datetime.now()
        db.session.commit()
    else:
        # If we didn't create an Application record yet, do so now.
        new_app = Application(user_id=user_id, job_id=job_id, status='Applied', applied_at=datetime.now())
        db.session.add(new_app)
        db.session.commit()

    print(f"Applied for {job.title} on behalf of {user.email} at {datetime.now()}")


# ============ ROUTES ============

@app.route('/register', methods=['POST'])
def register():
    """
    Register a new user. In a production app, you must hash passwords.
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')
    location = data.get('location')
    experience = data.get('experience')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    user = User(email=email, password=password, location=location, experience=experience)
    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully'}), 201


@app.route('/login', methods=['POST'])
def login():
    """
    Simple login endpoint. Again, use hashed passwords in production.
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if user and user.password == password:
        # In production, generate a JWT or session token
        return jsonify({'message': 'Login successful', 'user_id': user.id}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """
    Endpoint to upload and parse the resume, then store the file path for the user.
    """
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Invalid user ID'}), 400

    file = request.files.get('resume')
    if not file:
        return jsonify({'error': 'No resume file uploaded'}), 400

    filename = secure_filename(file.filename)
    unique_filename = str(uuid.uuid4()) + "_" + filename
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(file_path)

    # Parse resume
    parsed_data = parse_resume(file_path)

    # Update user with the resume path
    user.resume_path = file_path
    db.session.commit()

    return jsonify({
        'message': 'Resume uploaded successfully',
        'parsed_data': parsed_data
    }), 200


@app.route('/search_jobs', methods=['GET'])
def search_jobs_route():
    """
    Search for jobs based on user_id's criteria (location, experience).
    Optionally add a 'keyword' query param.
    """
    user_id = request.args.get('user_id')
    keyword = request.args.get('keyword', '')

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Invalid user ID'}), 400

    jobs = scrape_jobs(keyword, user.location)

    # Store or refresh them in the DB (optional)
    # For demonstration, let's just upsert them.
    saved_jobs = []
    for j in jobs:
        existing_job = Job.query.filter_by(
            title=j['title'],
            company=j['company'],
            location=j['location'],
            apply_link=j['apply_link']
        ).first()

        if not existing_job:
            new_job = Job(
                title=j['title'],
                company=j['company'],
                location=j['location'],
                apply_link=j['apply_link']
            )
            db.session.add(new_job)
            db.session.commit()
            saved_jobs.append(new_job)
        else:
            saved_jobs.append(existing_job)

    # Transform for JSON response
    response_jobs = []
    for sj in saved_jobs:
        response_jobs.append({
            'job_id': sj.id,
            'title': sj.title,
            'company': sj.company,
            'location': sj.location,
            'apply_link': sj.apply_link
        })

    return jsonify({'jobs': response_jobs}), 200


@app.route('/apply_job', methods=['POST'])
def apply_job():
    """
    Immediately apply to a job or schedule it in the future.
    JSON Body:
    {
      "user_id": 1,
      "job_id": 2,
      "schedule_time": "2025-01-20 10:00:00" (optional)
    }
    """
    data = request.json
    user_id = data.get('user_id')
    job_id = data.get('job_id')
    schedule_time_str = data.get('schedule_time')  # e.g. "2025-01-20 10:00:00"

    user = User.query.get(user_id)
    job = Job.query.get(job_id)
    if not user or not job:
        return jsonify({'error': 'Invalid user or job ID'}), 400

    # Check if there's an existing application record
    application = Application.query.filter_by(user_id=user_id, job_id=job_id).first()
    if application:
        return jsonify({'error': 'Already applied or pending application'}), 400

    # Create a new pending application
    new_app = Application(user_id=user_id, job_id=job_id, status='Pending')
    db.session.add(new_app)
    db.session.commit()

    if schedule_time_str:
        # Parse schedule time
        try:
            schedule_time = datetime.strptime(schedule_time_str, "%Y-%m-%d %H:%M:%S")
            schedule_job_application(user_id, job_id, schedule_time)
            return jsonify({'message': f'Application scheduled at {schedule_time_str}'}), 200
        except ValueError:
            return jsonify({'error': 'Invalid date/time format. Use YYYY-MM-DD HH:MM:SS'}), 400
    else:
        # Apply immediately
        execute_application(user_id, job_id)
        return jsonify({'message': 'Application executed immediately'}), 200


@app.route('/application_status', methods=['GET'])
def application_status():
    """
    Get the status of a user's applications.
    /application_status?user_id=1
    """
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'Invalid user ID'}), 400

    apps = Application.query.filter_by(user_id=user.id).all()
    result = []
    for a in apps:
        job = Job.query.get(a.job_id)
        result.append({
            'application_id': a.id,
            'job_title': job.title if job else 'Unknown',
            'company': job.company if job else 'Unknown',
            'status': a.status,
            'applied_at': a.applied_at.strftime('%Y-%m-%d %H:%M:%S') if a.applied_at else None
        })

    return jsonify({'applications': result}), 200


# ============ MAIN ============

if __name__ == '__main__':
    app.run(debug=True)


