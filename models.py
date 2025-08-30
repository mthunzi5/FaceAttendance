
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Create a SQLAlchemy instance. This will be used to interact with our database.
db = SQLAlchemy()


class Student(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id_number = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(120), unique=True, nullable=False)  # email
    face_encoding = db.Column(db.LargeBinary, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def __repr__(self):
        return f"Student('{self.name}', '{self.student_id_number}', '{self.username}')"


class Lecturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def __repr__(self):
        return f"Lecturer('{self.username}')"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
  
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'), nullable=False)

    def __repr__(self):
        return f"Course('{self.name}')"


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
   
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
   
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    
    date_recorded = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
   
    is_present = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"Attendance('{self.student_id}', '{self.date_recorded}')"

# Note: We'll set up the database and create these tables in the next step.
# Admin model for authentication
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    


# Register model for saved attendance registers
class Register(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_name = db.Column(db.String(100), nullable=False)
    lecturer_name = db.Column(db.String(100), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    student_ids = db.Column(db.Text, nullable=False)  # Comma-separated student IDs
