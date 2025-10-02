from flask import flash
from flask import session, redirect, url_for, render_template
from models import db, Student, Admin,AttendanceRecord, Lecturer, Qualification, Module
from werkzeug.security import generate_password_hash, check_password_hash
import os
import numpy as np
import datetime
import face_recognition
from flask import Flask, request, jsonify
from models import db, Student

from functools import wraps




# Initialize the Flask application
app = Flask(__name__)

# Configure the database connection string.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database with the Flask app.
db.init_app(app)

# Global variables to store face encodings and student IDs.
# We'll load these once when the application starts to improve performance.
known_face_encodings = []
known_student_ids = []

def load_known_faces():
    """
    Loads all student face encodings from the database into memory.
    This function is called once at application startup.
    """
    global known_face_encodings, known_student_ids
    with app.app_context():
        # Query all students from the database
        students = Student.query.all()
        # Clear existing lists
        known_face_encodings = []
        known_student_ids = []
        for student in students:
            # Convert the binary face encoding from the database back to a NumPy array
            face_array = np.frombuffer(student.face_encoding, dtype=np.float64)
            known_face_encodings.append(face_array)
            known_student_ids.append(student.student_id_number)
        print(f"Loaded {len(known_face_encodings)} student face encodings.")

# A command-line function to create all database tables.
@app.cli.command("create-db")
def create_db():
    """Create all database tables."""
    with app.app_context():
        db.create_all()
        print("Database tables created successfully.")

@app.cli.command("load-faces")
def load_faces_command():
    """Command-line command to load known faces."""
    load_known_faces()

# Define a basic route.
@app.route('/')
def home():
    """Render the home page with navigation links."""
    from flask import render_template
    import datetime
    user = session.get('user')
    role = session.get('role')
    current_year = datetime.datetime.now().year
    return render_template("home.html", user=user, role=role, current_year=current_year)



# Helper: login required decorator

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Only admin can enroll students
@app.route('/enroll', methods=['GET', 'POST'])
@login_required(role='admin')
def enroll_student():
    """
    Handles both GET (show form) and POST (process enrollment).
    """
    from models import Qualification
    import datetime
    current_year = datetime.datetime.now().year

    if request.method == 'GET':
        qualifications = Qualification.query.all()
        return render_template('enroll.html', qualifications=qualifications, current_year=current_year)

    # POST: process enrollment (AJAX expects JSON response)
    if 'student_id' not in request.form or 'image' not in request.files or 'student_username' not in request.form or 'student_password' not in request.form or 'qualification_id' not in request.form:
        return jsonify({"error": "Missing required fields"}), 400

    student_id = request.form['student_id']
    student_username = request.form['student_username']  # This should be an email
    student_password = request.form['student_password']
    qualification_id = request.form['qualification_id']
    image_file = request.files['image']

    with app.app_context():
        existing_student = Student.query.filter_by(student_id_number=student_id).first()
        if existing_student:
            return jsonify({"error": "Student with this ID already exists"}), 409

    try:
        import PIL.Image
        image = face_recognition.load_image_file(image_file)
        face_locations_list = face_recognition.face_locations(image)
        if not face_locations_list:
            return jsonify({"error": "No face found in the image"}), 400
        face_encoding = face_recognition.face_encodings(image, face_locations_list)[0]

        # Check for duplicate face encoding (same person already enrolled)
        if known_face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            if True in matches:
                return jsonify({"error": "Student with this face is already enrolled."}), 409

        # Save the uploaded image to static/student_photos/{student_id}.jpg
        save_dir = os.path.join(app.root_path, 'static', 'student_photos')
        os.makedirs(save_dir, exist_ok=True)
        image_file.stream.seek(0)
        img = PIL.Image.open(image_file.stream)
        img.save(os.path.join(save_dir, f'{student_id}.jpg'))

        new_student = Student(
            student_id_number=student_id,
            name=f"Student {student_id}",
            username=student_username,
            face_encoding=face_encoding.tobytes(),
            qualification_id=qualification_id
        )
        new_student.set_password(student_password)
        with app.app_context():
            db.session.add(new_student)
            db.session.commit()
        load_known_faces()
        return jsonify({"message": "Student enrolled successfully!", "student_id": student_id}), 201
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


# Mark Attendance route
@app.route('/attendance', methods=['GET', 'POST'])
def mark_attendance():
    from flask import render_template
    import datetime
    if request.method == 'GET':
        current_year = datetime.datetime.now().year
        return render_template('attendance.html', current_year=current_year)
    # POST: process uploaded group photo
    if 'image' not in request.files:
        return render_template('attendance.html', error="No image uploaded")
    image_file = request.files['image']
    try:
        image = face_recognition.load_image_file(image_file)
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        if not face_encodings:
            # Redirect to results page with a special flag for no faces detected
            from flask import redirect, url_for
            return redirect(url_for('attendance_results', students='', no_faces='1'))
        matched_students = set()
        for encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, encoding, tolerance=0.5)
            for idx, is_match in enumerate(matches):
                if is_match:
                    matched_students.add(known_student_ids[idx])
        matched_students = list(matched_students)
        from flask import redirect, url_for
        if matched_students:
            ids_str = ','.join(matched_students)
            return redirect(url_for('attendance_results', students=ids_str))
        else:
            # Faces detected, but no students matched
            return redirect(url_for('attendance_results', students='', no_students='1'))
    except Exception as e:
        print(f"Attendance error: {e}")
        return render_template('attendance.html', error="An internal error occurred")




# Edit student route
@app.route('/students/<student_id>/edit', methods=['GET', 'POST'])
def edit_student(student_id):
    from flask import render_template, request, redirect, url_for
    import datetime
    with app.app_context():
        student = Student.query.filter_by(student_id_number=student_id).first()
        if not student:
            return "Student not found", 404
        if request.method == 'POST':
            student.name = request.form['name']
            db.session.commit()
            return redirect(url_for('view_students'))
    current_year = datetime.datetime.now().year
    return render_template('edit_student.html', student=student, current_year=current_year)

# Delete student route
@app.route('/students/<student_id>/delete', methods=['POST'])
def delete_student(student_id):
    from flask import redirect, url_for
    with app.app_context():
        student = Student.query.filter_by(student_id_number=student_id).first()
        if student:
            db.session.delete(student)
            db.session.commit()
            # Optionally, delete the photo file
            photo_path = os.path.join(app.root_path, 'static', 'student_photos', f'{student_id}.jpg')
            if os.path.exists(photo_path):
                os.remove(photo_path)
        load_known_faces()
    return redirect(url_for('view_students'))




# View Students route

from sqlalchemy.orm import joinedload

@app.route('/students', methods=['GET'])
def view_students():
    from flask import render_template
    import datetime
    students = Student.query.options(joinedload(Student.qualification)).all()
    current_year = datetime.datetime.now().year
    return render_template('students_list.html', students=students, current_year=current_year)


# Mark Register route
@app.route('/mark-register', methods=['GET', 'POST'])
@login_required(role='lecturer')
def mark_register():
    from flask import render_template, request, session
    from models import Qualification, Module
    import datetime

    qualifications = Qualification.query.all()
    modules = Module.query.all()

    if request.method == 'GET':
        current_year = datetime.datetime.now().year
        return render_template(
            'mark_register.html',
            qualifications=qualifications,
            modules=modules,
            current_year=current_year
        )
    # POST: Lecturer selects qualification and module, uploads image, awards marks
    qualification_id = request.form.get('qualification_id')
    module_id = request.form.get('module_id')
    attendance_time = datetime.datetime.now()
    marks_dict = {}  # student_id_number -> marks

    # Get marks for present students
    for key in request.form:
        if key.startswith('marks_'):
            sid = key.split('_')[1]
            marks_dict[sid] = int(request.form[key])

    image_file = None
    if 'image' in request.files:
        image_file = request.files['image']
    elif 'camera_image' in request.form and request.form['camera_image']:
        import base64, io, PIL.Image
        data_url = request.form['camera_image']
        header, encoded = data_url.split(',', 1)
        img_bytes = base64.b64decode(encoded)
        image_file = io.BytesIO(img_bytes)

    present_student_ids = []
    students = []
    if image_file:
        try:
            import PIL.Image
            image = face_recognition.load_image_file(image_file)
            face_locations = face_recognition.face_locations(image)
            face_encodings = face_recognition.face_encodings(image, face_locations)
            if face_encodings:
                matched_students = set()
                for encoding in face_encodings:
                    matches = face_recognition.compare_faces(known_face_encodings, encoding, tolerance=0.5)
                    for idx, is_match in enumerate(matches):
                        if is_match:
                            matched_students.add(known_student_ids[idx])
                present_student_ids = list(matched_students)
        except Exception as e:
            print(f"Mark register error: {e}")

    # Get all students for this qualification
    all_students = Student.query.filter_by(qualification_id=qualification_id).all()

    # Save attendance records for all students in the qualification
    for student in all_students:
        status = "Present" if student.student_id_number in present_student_ids else "Absent"
        marks = marks_dict.get(student.student_id_number, 0) if status == "Present" else 0
        record = AttendanceRecord(
            student_id=student.id,
            module_id=module_id,
            qualification_id=qualification_id,
            date_time=attendance_time,
            marks=marks,
            status=status
        )
        db.session.add(record)
    db.session.commit()

    # Prepare students for results template (only present students)
    students = Student.query.filter(Student.student_id_number.in_(present_student_ids)).all() if present_student_ids else []

    current_year = datetime.datetime.now().year
    return render_template(
        'mark_register_results.html',
        students=students,
        module_id=module_id,
        qualification_id=qualification_id,
        lecturer_name=session.get('user', 'Unknown'),
        attendance_time=attendance_time.strftime('%Y-%m-%d %H:%M:%S'),
        current_year=current_year
    )



# Export register as PDF
@app.route('/export-register', methods=['POST'])
@login_required(role='lecturer')
def export_register():
    from flask import request, send_file
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    module_name = request.form.get('module_name', 'Unknown')
    lecturer_name = request.form.get('lecturer_name', 'Unknown')
    attendance_time = request.form.get('attendance_time', '')
    student_ids = request.form.get('student_ids', '').split(',') if request.form.get('student_ids') else []
    students = []
    if student_ids and student_ids[0]:
        with app.app_context():
            students = Student.query.filter(Student.student_id_number.in_(student_ids)).all()
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Register Results")
    p.setFont("Helvetica", 12)
    y = 720
    p.drawString(100, y, f"Module: {module_name}")
    y -= 20
    p.drawString(100, y, f"Lecturer: {lecturer_name}")
    y -= 20
    p.drawString(100, y, f"Date/Time: {attendance_time}")
    y -= 40
    p.drawString(100, y, "Student ID")
    p.drawString(250, y, "Name")
    y -= 20
    if students:
        for s in students:
            p.drawString(100, y, str(s.student_id_number))
            p.drawString(250, y, s.name)
            y -= 20
    else:
        p.drawString(100, y, "No students attended.")
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="register.pdf", mimetype="application/pdf")

# Save register
@app.route('/save-register', methods=['POST'])
@login_required(role='lecturer')
def save_register():
    from models import Register
    from flask import request, flash, redirect, url_for
    module_name = request.form.get('module_name', 'Unknown')
    lecturer_name = request.form.get('lecturer_name', 'Unknown')
    attendance_time_str = request.form.get('attendance_time', '')
    student_ids = request.form.get('student_ids', '')
    import datetime
    # Convert string to datetime object
    if attendance_time_str:
        try:
            attendance_time = datetime.datetime.strptime(attendance_time_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            attendance_time = datetime.datetime.now()
    else:
        attendance_time = datetime.datetime.now()
    with app.app_context():
        reg = Register(module_name=module_name, lecturer_name=lecturer_name, date_time=attendance_time, student_ids=student_ids)
        db.session.add(reg)
        db.session.commit()
    flash('Register saved.')
    return redirect(url_for('list_registers'))
# List saved registers
@app.route('/registers', methods=['GET'])
@login_required(role='lecturer')
def list_registers():
    from flask import render_template
    from models import Register
    import datetime
    with app.app_context():
        registers = Register.query.order_by(Register.date_time.desc()).all()
    current_year = datetime.datetime.now().year
    return render_template('registers_list.html', registers=registers, current_year=current_year)

# Award marks to all attended students
@app.route('/award-marks', methods=['POST'])
@login_required(role='lecturer')
def award_marks():
    from flask import request, redirect, url_for, flash
    from models import Student, AttendanceRecord, db

    module_id = request.form.get('module_id')
    qualification_id = request.form.get('qualification_id')
    student_ids = request.form.get('student_ids', '').split(',') if request.form.get('student_ids') else []
    marks = int(request.form.get('marks', 0))
    attendance_time = datetime.datetime.now()

    # Get all students for this qualification
    all_students = Student.query.filter_by(qualification_id=qualification_id).all()

    for student in all_students:
        is_present = student.student_id_number in student_ids
        record = AttendanceRecord(
            student_id=student.id,
            module_id=module_id,
            qualification_id=qualification_id,
            date_time=attendance_time,
            marks=marks if is_present else 0,
            status="Present" if is_present else "Absent"
        )
        db.session.add(record)
    db.session.commit()

    flash("Marks awarded and attendance records created.")
    return redirect(url_for('mark_register'))




# Live Camera Attendance route
@app.route('/live-attendance', methods=['GET', 'POST'])
@login_required(role='lecturer')
def live_attendance():
    from flask import render_template, request, session, redirect, url_for, jsonify
    import base64, io, datetime
    from models import Student, AttendanceRecord, Qualification, Module, db

    if request.method == 'GET':
        current_year = datetime.datetime.now().year
        qualifications = Qualification.query.all()
        modules = Module.query.all()
        return render_template('live_attendance.html', current_year=current_year, qualifications=qualifications, modules=modules)

    # POST: process camera image, qualification, and module
    data = request.get_json()
    if not data or 'camera_image' not in data or 'qualification_id' not in data or 'module_id' not in data:
        return jsonify({"error": "Missing required data."}), 400

    data_url = data['camera_image']
    qualification_id = data['qualification_id']
    module_id = data['module_id']
    lecturer_name = session.get('user', 'Unknown')
    attendance_time = datetime.datetime.now()
    students = []
    present_student_ids = []

    try:
        header, encoded = data_url.split(',', 1)
        img_bytes = base64.b64decode(encoded)
        image_file = io.BytesIO(img_bytes)
        import PIL.Image
        image = face_recognition.load_image_file(image_file)
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        if face_encodings:
            matched_students = set()
            for encoding in face_encodings:
                matches = face_recognition.compare_faces(known_face_encodings, encoding, tolerance=0.5)
                for idx, is_match in enumerate(matches):
                    if is_match:
                        matched_students.add(known_student_ids[idx])
            present_student_ids = list(matched_students)
        # Get all students for this qualification
        all_students = Student.query.filter_by(qualification_id=qualification_id).all()
        # Save attendance records for all students in the qualification
        for student in all_students:
            status = "Present" if student.student_id_number in present_student_ids else "Absent"
            marks = 1 if status == "Present" else 0  # You can adjust marks logic as needed
            record = AttendanceRecord(
                student_id=student.id,
                module_id=module_id,
                qualification_id=qualification_id,
                date_time=attendance_time,
                marks=marks,
                status=status
            )
            db.session.add(record)
        db.session.commit()
        # Prepare students for template (only present students)
        students = Student.query.filter(Student.student_id_number.in_(present_student_ids)).all() if present_student_ids else []
        current_year = datetime.datetime.now().year
        return render_template(
            'live_register_results.html',
            students=students,
            module_id=module_id,
            qualification_id=qualification_id,
            lecturer_name=lecturer_name,
            attendance_time=attendance_time.strftime('%Y-%m-%d %H:%M:%S'),
            current_year=current_year
        )
    except Exception as e:
        print(f"Live attendance error: {e}")
        current_year = datetime.datetime.now().year
        return render_template(
            'live_register_results.html',
            students=[],
            module_id=module_id,
            qualification_id=qualification_id,
            lecturer_name=lecturer_name,
            attendance_time=attendance_time.strftime('%Y-%m-%d %H:%M:%S'),
            current_year=current_year
        )

app.secret_key = 'supersecretkey'  # Change for production
# Helper: login required decorator

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
# Hardcoded admin creation (run once at startup)
with app.app_context():
    # Create hardcoded admin after tables exist
    db.create_all()
    if not Admin.query.filter_by(username='admin').first():
        admin = Admin(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
    load_known_faces()

# Login route

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    import datetime
    current_year = datetime.datetime.now().year
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Admin.query.filter_by(username=username).first()
        role = 'admin'
        if not user:
            user = Lecturer.query.filter_by(username=username).first()
            role = 'lecturer'
        if not user:
            user = Student.query.filter_by(username=username).first()
            role = 'student'
        if user and user.check_password(password):
            if role == 'student':
                session['student_id'] = user.student_id_number
                return redirect(url_for('student_dashboard'))
            else:
                session['user'] = username
                session['role'] = role
                return redirect(url_for('home'))
        else:
            error = 'Invalid credentials.'
    return render_template('login.html', error=error, current_year=current_year)

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))
# Admin creates lecturers
@app.route('/create-lecturer', methods=['GET', 'POST'])
@login_required(role='admin')
def create_lecturer():
    error = None
    success = None
    import datetime
    current_year = datetime.datetime.now().year
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if Lecturer.query.filter_by(username=username).first():
            error = 'Lecturer already exists.'
        else:
            lecturer = Lecturer(name=username, username=username)
            lecturer.set_password(password)
            db.session.add(lecturer)
            db.session.commit()
            success = 'Lecturer created successfully.'
    return render_template('create_lecturer.html', error=error, success=success, current_year=current_year)
# View Lecturers route
@app.route('/lecturers', methods=['GET'])
@login_required(role='admin')
def view_lecturers():
    from flask import render_template
    import datetime
    with app.app_context():
        lecturers = Lecturer.query.all()
    current_year = datetime.datetime.now().year
    return render_template('lecturers_list.html', lecturers=lecturers, current_year=current_year)

# Edit Lecturer route
@app.route('/lecturers/<int:lecturer_id>/edit', methods=['GET', 'POST'])
@login_required(role='admin')
def edit_lecturer(lecturer_id):
    from flask import render_template, request, redirect, url_for
    import datetime
    with app.app_context():
        lecturer = Lecturer.query.get(lecturer_id)
        if not lecturer:
            return "Lecturer not found", 404
        if request.method == 'POST':
            lecturer.name = request.form['name']
            lecturer.username = request.form['username']
            db.session.commit()
            return redirect(url_for('view_lecturers'))
    current_year = datetime.datetime.now().year
    return render_template('edit_lecturer.html', lecturer=lecturer, current_year=current_year)

# Delete Lecturer route
@app.route('/lecturers/<int:lecturer_id>/delete', methods=['POST'])
@login_required(role='admin')
def delete_lecturer(lecturer_id):
    from flask import redirect, url_for
    with app.app_context():
        lecturer = Lecturer.query.get(lecturer_id)
        if lecturer:
            db.session.delete(lecturer)
            db.session.commit()
    return redirect(url_for('view_lecturers'))



# Student login route
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    from flask import render_template, request, session, redirect, url_for
    import datetime
    current_year = datetime.datetime.now().year
    error = None
    if request.method == 'POST':
        student_username = request.form['student_username']
        password = request.form['student_password']
        with app.app_context():
            student = Student.query.filter_by(username=student_username).first()
        if student and student.check_password(password):
            session['student_id'] = student.student_id_number
            return redirect(url_for('student_dashboard'))
        else:
            error = 'Invalid email or password.'
    return render_template('student_login.html', error=error, current_year=current_year)

# Student dashboard route
@app.route('/student-dashboard')
def student_dashboard():
    from flask import render_template, session, redirect, url_for
    import datetime
    from sqlalchemy.orm import joinedload

    current_year = datetime.datetime.now().year
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('student_login'))
    with app.app_context():
        student = Student.query.filter_by(student_id_number=student_id).first()
        attendance_records = AttendanceRecord.query.options(
            joinedload(AttendanceRecord.module)
        ).filter_by(student_id=student.id).order_by(AttendanceRecord.date_time.desc()).all()
    return render_template(
        'student_dashboard.html',
        student=student,
        attendance_records=attendance_records,
        current_year=current_year
    )


@app.route('/qualifications', methods=['GET', 'POST'])
@login_required(role='admin')
def manage_qualifications():
    from flask import render_template, request, redirect, url_for
    import datetime
    current_year = datetime.datetime.now().year
    error = None
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        if Qualification.query.filter_by(name=name).first():
            error = "Qualification already exists."
        else:
            q = Qualification(name=name, description=description)
            db.session.add(q)
            db.session.commit()
            return redirect(url_for('manage_qualifications'))
    qualifications = Qualification.query.all()
    return render_template('qualifications.html', qualifications=qualifications, error=error, current_year=current_year)

@app.route('/modules', methods=['GET', 'POST'])
@login_required(role='admin')
def manage_modules():
    from flask import render_template, request, redirect, url_for
    import datetime
    current_year = datetime.datetime.now().year
    error = None
    qualifications = Qualification.query.all()
    if request.method == 'POST':
        name = request.form['name']
        qualification_id = request.form['qualification_id']
        if Module.query.filter_by(name=name, qualification_id=qualification_id).first():
            error = "Module already exists for this qualification."
        else:
            m = Module(name=name, qualification_id=qualification_id)
            db.session.add(m)
            db.session.commit()
            return redirect(url_for('manage_modules'))
    modules = Module.query.all()
    return render_template('modules.html', modules=modules, qualifications=qualifications, error=error, current_year=current_year)

@app.route('/attendance-records')
@login_required(role='student')
def attendance_records():
    student_id = session.get('user_id')
    records = AttendanceRecord.query.options(
        joinedload(AttendanceRecord.module),
        joinedload(AttendanceRecord.qualification)
    ).filter_by(student_id=student_id).order_by(AttendanceRecord.date_time.desc()).all()
    return render_template('attendance_records.html', records=records)




































# Production-safe initialization
def initialize_app():
    with app.app_context():
        db.create_all()
        # Create hardcoded admin after tables exist
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
        load_known_faces()

initialize_app()

# Only run the development server if executed directly

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)