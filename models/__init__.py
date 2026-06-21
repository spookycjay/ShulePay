# models/__init__.py
from datetime import datetime
from extension import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Numeric


# ========================= Association Tables =========================

parent_student = db.Table(
    'parent_student',
    db.Column('parent_id', db.Integer, db.ForeignKey('parents.id'), primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('students.id'), primary_key=True)
)


# ========================= School Model =========================

class School(db.Model):
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(150), nullable=True, unique=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='school', lazy=True)
    classes = db.relationship('Classes', backref='school', lazy=True)
    students = db.relationship('Student', backref='school', lazy=True)
    parents = db.relationship('Parent', backref='school', lazy=True)
    fee_structures = db.relationship('FeeStructure', backref='school', lazy=True)
    payments = db.relationship('Payment', backref='school', lazy=True)

    def __repr__(self):
        return f"<School {self.name}>"


# ========================= User Model =========================

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    parent_profile = db.relationship('Parent', backref='user', uselist=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_unread_notifications_count(self):
        return Notification.query.filter_by(
            user_id=self.id,
            is_read=False
        ).count()

    def __repr__(self):
        return f"<User {self.email}>"


# ========================= Classes Model =========================

class Classes(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)

    # Relationships
    students = db.relationship("Student", backref="class_room", lazy=True)
    fee_structures = db.relationship("FeeStructure", backref="class_room", lazy=True)

    def __repr__(self):
        return f"<Classes {self.name}>"


# ========================= Student Model =========================

class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    admission_number = db.Column(db.String(100), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)

    # Relationships
    payments = db.relationship("Payment", backref="student", lazy=True)
    mpesa_requests = db.relationship('MpesaRequest', backref='student', lazy=True)

    def __repr__(self):
        return f"<Student {self.first_name} {self.last_name}>"


# ========================= Parent Model =========================

class Parent(db.Model):
    __tablename__ = "parents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)

    # Relationships
    students = db.relationship(
        'Student',
        secondary=parent_student,
        backref=db.backref('parents', lazy='dynamic')
    )

    def __repr__(self):
        return f"<Parent {self.first_name} {self.last_name}>"


# ========================= FeeStructure Model =========================

class FeeStructure(db.Model):
    __tablename__ = "fee_structures"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    term = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<FeeStructure Class {self.class_id} - {self.amount}>"


# ========================= Payment Model =========================

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)  # NEW
    amount = db.Column(Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50), default='cash')
    status = db.Column(db.String(50), default='completed')
    reference = db.Column(db.String(150))
    phone_number = db.Column(db.String(15))
    mpesa_code = db.Column(db.String(20))
    checkout_request_id = db.Column(db.String(100))
    term = db.Column(db.String(50), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    
    def __repr__(self):
        return f"<Payment {self.amount} for Student {self.student_id}>"

# ========================= Notification Model =========================

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_type = db.Column(db.String(50), nullable=False)

    # Relationships
    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f"<Notification {self.title} for User {self.user_id}>"

# ========================= MpesaRequest Model =========================

class MpesaRequest(db.Model):
    __tablename__ = 'mpesa_requests'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    checkout_request_id = db.Column(db.String(100), unique=True)
    merchant_request_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    result_code = db.Column(db.String(10))
    result_desc = db.Column(db.String(255))
    mpesa_code = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<MpesaRequest {self.checkout_request_id}>"
    
    # ========================= Invoice Model =========================

class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False)
    total_amount = db.Column(Numeric(10, 2), nullable=False, default=0)
    paid_amount = db.Column(Numeric(10, 2), nullable=False, default=0)
    balance = db.Column(Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(50), default='unpaid')  # unpaid/partial/paid
    term = db.Column(db.String(50), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship('Student', backref='invoices')
    school = db.relationship('School', backref='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='invoice', lazy=True)

    def update_balance(self):
        """Recalculate balance and status"""
        self.paid_amount = sum(
            float(p.amount) for p in self.payments
            if p.status == 'completed'
        )
        self.balance = float(self.total_amount) - float(self.paid_amount)
        if self.balance <= 0:
            self.status = 'paid'
        elif float(self.paid_amount) > 0:
            self.status = 'partial'
        else:
            self.status = 'unpaid'

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"


# ========================= InvoiceItem Model =========================

class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    fee_structure_id = db.Column(db.Integer, db.ForeignKey("fee_structures.id"), nullable=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)

    def __repr__(self):
        return f"<InvoiceItem {self.description} - {self.amount}>"