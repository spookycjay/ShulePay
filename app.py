from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_migrate import Migrate
from models import (Notification, User, db, Student, Parent, Classes, 
                    Payment, FeeStructure, MpesaRequest, School, Invoice, InvoiceItem)
from datetime import datetime
from decimal import Decimal
import json
from mpesa import stk_push
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'mysql+pymysql://root@localhost/shulepay'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'


# ========================= Helpers =========================

def get_current_term():
    """Automatically determine current school term by month."""
    month = datetime.now().month
    if month in [1, 2, 3, 4]:
        return "Term 1"
    elif month in [5, 6, 7, 8]:
        return "Term 2"
    else:
        return "Term 3"


def create_notification(user_id, title, message, notif_type='info'):
    """Create a notification for a user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notif_type
    )
    db.session.add(notification)
    db.session.commit()


# ========================= Login Manager =========================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ========================= Context Processors =========================

@app.context_processor
def inject_unread_notifications():
    if current_user.is_authenticated:
        unread_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
    else:
        unread_count = 0
    return dict(unread_count=unread_count)


@app.context_processor
def inject_now():
    return {'now': datetime.now()}


# ========================= Before Request =========================

@app.before_request
def check_fee_notifications():
    """Send fee balance notifications to parents on dashboard visit."""
    if not current_user.is_authenticated or current_user.role != 'parent':
        return
    if request.endpoint == 'static':
        return
    if request.endpoint != 'parent_dashboard':
        return

    parent = current_user.parent_profile
    if not parent:
        return

    current_year = datetime.now().year
    current_term = get_current_term()

    for student in parent.students:
        total_fees = db.session.query(
            db.func.coalesce(db.func.sum(FeeStructure.amount), 0)
        ).filter_by(
            class_id=student.class_id,
            year=current_year,
            term=current_term
        ).scalar() or 0

        total_paid = db.session.query(
            db.func.coalesce(db.func.sum(Payment.amount), 0)
        ).filter_by(
            student_id=student.id,
            status='completed'
        ).scalar() or 0

        balance = float(total_fees) - float(total_paid)

        if balance > 0:
            from datetime import date
            already_notified_today = Notification.query.filter(
                Notification.user_id == current_user.id,
                Notification.notification_type == 'fee_due',
                Notification.message.contains(student.first_name),
                db.func.date(Notification.created_at) == date.today()
            ).first()

            if not already_notified_today:
                create_notification(
                    user_id=current_user.id,
                    title="Fee Balance Reminder",
                    message=f"{student.first_name} has an outstanding balance of KSh {balance:,.2f}",
                    notif_type="fee_due"
                )


# ========================= Auth Routes =========================

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'parent':
            return redirect(url_for('parent_dashboard'))
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('login.html')

        user = User.query.filter(db.func.lower(User.email) == email).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'parent':
                return redirect(url_for('parent_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


# ========================= School Routes =========================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        school_name = request.form.get('school_name', '').strip()
        admin_name = request.form.get('admin_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not all([school_name, admin_name, email, phone, password, confirm_password]):
            flash('All fields are required!', 'danger')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters!', 'danger')
            return render_template('auth/register.html')

        if User.query.filter(db.func.lower(User.email) == email).first():
            flash('An account with this email already exists!', 'danger')
            return render_template('auth/register.html')

        if School.query.filter(
            db.func.lower(School.name) == school_name.lower()
        ).first():
            flash('A school with this name already exists!', 'danger')
            return render_template('auth/register.html')

        try:
            new_school = School(
                name=school_name,
                email=email,
                phone=phone
            )
            db.session.add(new_school)
            db.session.flush()

            new_user = User(
                username=email,
                email=email,
                role='admin',
                school_id=new_school.id
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            flash(f'School "{school_name}" registered! Please login.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error registering school: {str(e)}', 'danger')
            return render_template('auth/register.html')

    return render_template('register.html')


@app.route('/admin/school/settings', methods=['GET', 'POST'])
@login_required
def school_settings():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    school = db.session.get(School, current_user.school_id)
    if not school:
        flash('No school found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        school_name = request.form.get('school_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()

        if not school_name:
            flash('School name is required!', 'danger')
            return render_template('school_settings.html', school=school)

        try:
            school.name = school_name
            school.phone = phone
            school.address = address
            db.session.commit()
            flash('School settings updated successfully!', 'success')
            return redirect(url_for('school_settings'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating settings: {str(e)}', 'danger')

    return render_template('school_settings.html', school=school)


# ========================= Admin Routes =========================

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    school = db.session.get(School, current_user.school_id)

    total_students = Student.query.filter_by(
        school_id=current_user.school_id
    ).count()

    total_parents = Parent.query.filter_by(
        school_id=current_user.school_id
    ).count()

    total_classes = Classes.query.filter_by(
        school_id=current_user.school_id
    ).count()

    total_invoices = Invoice.query.filter_by(
        school_id=current_user.school_id
    ).count()

    total_unpaid = Invoice.query.filter_by(
        school_id=current_user.school_id,
        status='unpaid'
    ).count()

    today_payments = Payment.query.filter(
        Payment.school_id == current_user.school_id,
        db.func.date(Payment.payment_date) == db.func.current_date()
    ).all()

    total_today = sum(float(payment.amount) for payment in today_payments)

    return render_template(
        'admin_dashboard.html',
        school=school,
        students=total_students,
        parents=total_parents,
        classes=total_classes,
        total_invoices=total_invoices,
        total_unpaid=total_unpaid,
        payments=today_payments,
        total_today=total_today
    )


@app.route('/classes', methods=['GET', 'POST'])
@login_required
def manage_classes():
    if current_user.role != 'admin':
        flash("You do not have permission to manage classes.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        class_name = request.form.get('class_name', '').strip()

        if not class_name:
            flash("Class name is required.", "danger")
            return redirect(url_for('manage_classes'))

        existing = Classes.query.filter(
            db.func.lower(Classes.name) == class_name.lower(),
            Classes.school_id == current_user.school_id
        ).first()

        if existing:
            flash("This class already exists!", "warning")
        else:
            new_class = Classes(
                name=class_name,
                school_id=current_user.school_id
            )
            db.session.add(new_class)
            db.session.commit()
            flash(f"Class '{class_name}' successfully created!", "success")

        return redirect(url_for('manage_classes'))

    all_classes = Classes.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Classes.name.asc()).all()

    return render_template('add_classes.html', classes=all_classes)


@app.route('/admin/add_parent', methods=['GET', 'POST'])
@login_required
def add_parent():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if not all([first_name, last_name, email, phone, password]):
            flash("All fields are required!", "danger")
            return redirect(url_for('add_parent'))

        if User.query.filter(db.func.lower(User.email) == email).first():
            flash("A user with this email already exists!", "danger")
            return redirect(url_for('add_parent'))

        if Parent.query.filter(db.func.lower(Parent.email) == email).first():
            flash("A parent profile with this email already exists!", "danger")
            return redirect(url_for('add_parent'))

        try:
            new_user = User(
                username=email,
                email=email,
                role='parent',
                school_id=current_user.school_id
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            new_parent = Parent(
                user_id=new_user.id,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                school_id=current_user.school_id
            )
            db.session.add(new_parent)
            db.session.commit()
            flash(f"Parent account for {first_name} created successfully!", "success")
            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating parent account: {str(e)}", "danger")
            return redirect(url_for('add_parent'))

    return render_template('add_parent_account.html')


@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    all_classes = Classes.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Classes.name.asc()).all()

    all_parents = Parent.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Parent.first_name.asc()).all()

    if request.method == 'POST':
        admission_number = request.form.get('admission_number', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        class_id = request.form.get('class_id')
        parent_id = request.form.get('parent_id')

        if not all([admission_number, first_name, last_name, class_id, parent_id]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('add_student'))

        if Student.query.filter_by(admission_number=admission_number).first():
            flash('Admission Number already exists!', 'danger')
            return redirect(url_for('add_student'))

        try:
            new_student = Student(
                admission_number=admission_number,
                first_name=first_name,
                last_name=last_name,
                class_id=int(class_id),
                school_id=current_user.school_id
            )
            db.session.add(new_student)
            db.session.flush()

            parent = db.session.get(Parent, int(parent_id))
            if parent:
                parent.students.append(new_student)

            db.session.commit()
            flash(f'Student {first_name} {last_name} added successfully!', 'success')
            return redirect(url_for('view_students'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding student: {str(e)}', 'danger')
            return redirect(url_for('add_student'))

    return render_template('add_student.html', classes=all_classes, parents=all_parents)


@app.route('/students')
@login_required
def view_students():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    all_students = Student.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Student.first_name.asc()).all()

    return render_template('view_students.html', students=all_students)


@app.route('/fees/structure', methods=['GET', 'POST'])
@login_required
def set_fee_structure():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    all_classes = Classes.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Classes.name.asc()).all()

    all_structures = FeeStructure.query.filter_by(
        school_id=current_user.school_id
    ).order_by(FeeStructure.year.desc()).all()

    if request.method == 'POST':
        class_id = request.form.get('class_id')
        amount = request.form.get('amount')
        term = request.form.get('term', '').strip()
        year = request.form.get('year')

        if not all([class_id, amount, term, year]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('set_fee_structure'))

        try:
            new_fee = FeeStructure(
                class_id=int(class_id),
                amount=float(amount),
                term=term,
                year=int(year),
                school_id=current_user.school_id
            )
            db.session.add(new_fee)
            db.session.commit()
            flash('Fee structure added successfully!', 'success')
            return redirect(url_for('set_fee_structure'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('set_fee_structure'))

    return render_template('set_fees.html', structures=all_structures, classes=all_classes)


@app.route('/add_payment', defaults={'student_id': None}, methods=['GET', 'POST'])
@app.route('/add_payment/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_payment(student_id=None):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    students = Student.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Student.first_name, Student.last_name).all()

    selected_student = None
    if student_id is not None:
        selected_student = db.session.get(Student, student_id)
        if not selected_student:
            flash('Student not found.', 'danger')
            return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        form_student_id = request.form.get('student_id') or student_id
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method', 'cash')
        status = request.form.get('status', 'completed')
        reference = request.form.get('reference')

        if not form_student_id or not amount:
            flash('Student and amount are required.', 'danger')
            return redirect(request.url)

        try:
            amount = Decimal(amount)
        except Exception:
            flash('Invalid amount.', 'danger')
            return redirect(request.url)

        payment = Payment(
            student_id=int(form_student_id),
            amount=amount,
            payment_method=payment_method,
            status=status,
            reference=reference,
            school_id=current_user.school_id
        )
        db.session.add(payment)
        db.session.commit()

        student = db.session.get(Student, int(form_student_id))
        if student:
            for parent in student.parents:
                if parent.user:
                    create_notification(
                        user_id=parent.user.id,
                        title="✅ Payment Confirmed",
                        message=(
                            f"Payment of KSh {amount:,.2f} has been recorded for "
                            f"{student.first_name} {student.last_name} via "
                            f"{payment_method}. Reference: {reference or 'N/A'}."
                        ),
                        notif_type='payment_confirmed'
                    )

        flash('Payment added successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template(
        'add_payment.html',
        students=students,
        selected_student=selected_student
    )

@app.route('/payments')
@login_required
def view_payments():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    all_payments = Payment.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Payment.payment_date.desc()).all()

    return render_template('view_payments.html', payments=all_payments)


# ========================= Invoice Routes =========================
@app.route('/invoices')
@login_required
def view_invoices():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    invoices = Invoice.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Invoice.created_at.desc()).all()

    return render_template('invoices_index.html', invoices=invoices)

@app.route('/invoices/create', methods=['GET', 'POST'])
@login_required
def create_invoice():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    students = Student.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Student.first_name).all()

    fee_structures = FeeStructure.query.filter_by(
        school_id=current_user.school_id
    ).order_by(FeeStructure.term).all()

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        term = request.form.get('term', '').strip()
        year = request.form.get('year')
        due_date_str = request.form.get('due_date')
        fee_ids = request.form.getlist('fee_ids')

        if not all([student_id, term, year]):
            flash('Student, term and year are required!', 'danger')
            return redirect(url_for('create_invoice'))

        if not fee_ids:
            flash('Please select at least one fee item!', 'danger')
            return redirect(url_for('create_invoice'))

        try:
            last_invoice = Invoice.query.filter_by(
                school_id=current_user.school_id
            ).order_by(Invoice.id.desc()).first()

            next_number = (last_invoice.id + 1) if last_invoice else 1
            invoice_number = f"INV-{current_user.school_id:03d}-{next_number:04d}"

            due_date = None
            if due_date_str:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d')

            selected_fees = FeeStructure.query.filter(
                FeeStructure.id.in_([int(fid) for fid in fee_ids])
            ).all()

            total_amount = sum(float(f.amount) for f in selected_fees)

            invoice = Invoice(
                invoice_number=invoice_number,
                student_id=int(student_id),
                school_id=current_user.school_id,
                total_amount=total_amount,
                paid_amount=0,
                balance=total_amount,
                status='unpaid',
                term=term,
                year=int(year),
                due_date=due_date
            )
            db.session.add(invoice)
            db.session.flush()

            for fee in selected_fees:
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    fee_structure_id=fee.id,
                    description=f"{fee.term} - {fee.class_room.name} Fees",
                    amount=fee.amount
                )
                db.session.add(item)

            db.session.commit()

            student = db.session.get(Student, int(student_id))
            if student:
                for parent in student.parents:
                    if parent.user:
                        create_notification(
                            user_id=parent.user.id,
                            title="📄 New Invoice Generated",
                            message=(
                                f"A new invoice {invoice_number} of KSh {total_amount:,.2f} "
                                f"has been generated for {student.first_name} "
                                f"{student.last_name} for {term} {year}."
                            ),
                            notif_type='invoice_generated'
                        )

            flash(f'Invoice {invoice_number} created successfully!', 'success')
            return redirect(url_for('view_invoices'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating invoice: {str(e)}', 'danger')
            return redirect(url_for('create_invoice'))

    return render_template(
        'invoices_create.html',
        students=students,
        fee_structures=fee_structures,
        current_year=datetime.now().year
    )

@app.route('/invoices/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        abort(404)

    if invoice.school_id != current_user.school_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('view_invoices'))

    return render_template('invoices_detail.html', invoice=invoice)

@app.route('/invoices/<int:invoice_id>/pay', methods=['GET', 'POST'])
@login_required
def pay_invoice(invoice_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        abort(404)

    if invoice.school_id != current_user.school_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('view_invoices'))

    if request.method == 'POST':
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method', 'cash')
        reference = request.form.get('reference')

        if not amount:
            flash('Amount is required!', 'danger')
            return redirect(url_for('pay_invoice', invoice_id=invoice_id))

        try:
            amount = Decimal(amount)

            if amount > invoice.balance:
                flash(
                    f'Amount cannot exceed balance of KSh {invoice.balance:,.2f}!',
                    'danger'
                )
                return redirect(url_for('pay_invoice', invoice_id=invoice_id))

            payment = Payment(
                student_id=invoice.student_id,
                school_id=current_user.school_id,
                invoice_id=invoice.id,
                amount=amount,
                payment_method=payment_method,
                reference=reference,
                status='completed',
                term=invoice.term,
                year=invoice.year
            )
            db.session.add(payment)
            db.session.flush()

            invoice.update_balance()
            db.session.commit()

            student = db.session.get(Student, invoice.student_id)
            if student:
                for parent in student.parents:
                    if parent.user:
                        create_notification(
                            user_id=parent.user.id,
                            title="✅ Payment Received",
                            message=(
                                f"Payment of KSh {amount:,.2f} received for invoice "
                                f"{invoice.invoice_number}. "
                                f"Remaining balance: KSh {float(invoice.balance):,.2f}."
                            ),
                            notif_type='payment_confirmed'
                        )

            flash('Payment recorded successfully!', 'success')
            return redirect(url_for('view_invoice', invoice_id=invoice_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error recording payment: {str(e)}', 'danger')
            return redirect(url_for('pay_invoice', invoice_id=invoice_id))

    return render_template('invoices_pay.html', invoice=invoice)

@app.route('/invoices/<int:invoice_id>/delete', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        abort(404)

    if invoice.school_id != current_user.school_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('view_invoices'))

    try:
        db.session.delete(invoice)
        db.session.commit()
        flash('Invoice deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting invoice: {str(e)}', 'danger')

    return redirect(url_for('view_invoices'))

# ========================= Parent Routes =========================
@app.route('/parent/dashboard')
@login_required
def parent_dashboard():
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    if not parent:
        flash('No parent profile linked to this account. Contact admin.', 'danger')
        return redirect(url_for('login'))

    current_year = datetime.now().year
    current_term = get_current_term()

    student_info = []

    for student in parent.students:
        total_fees = db.session.query(
            db.func.coalesce(db.func.sum(FeeStructure.amount), 0)
        ).filter_by(
            class_id=student.class_id,
            year=current_year,
            term=current_term
        ).scalar() or 0

        total_paid = db.session.query(
            db.func.coalesce(db.func.sum(Payment.amount), 0)
        ).filter_by(
            student_id=student.id,
            status='completed'
        ).scalar() or 0

        total_fees = float(total_fees)
        total_paid = float(total_paid)
        balance = max(total_fees - total_paid, 0)

        payment_percentage = int((total_paid / total_fees * 100)) if total_fees > 0 else 0
        payment_percentage = min(payment_percentage, 100)

        fee_structure = FeeStructure.query.filter_by(
            class_id=student.class_id,
            year=current_year,
            term=current_term
        ).first()

        due_date = fee_structure.due_date if fee_structure else None
        is_overdue = False
        if due_date and balance > 0:
            is_overdue = datetime.now() > due_date

        page = request.args.get(f'page_{student.id}', 1, type=int)
        all_payments = Payment.query.filter_by(
            student_id=student.id
        ).order_by(Payment.payment_date.desc()).all()

        per_page = 5
        total_payments = len(all_payments)
        total_pages = max((total_payments + per_page - 1) // per_page, 1)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        paginated_payments = all_payments[start:start + per_page]

        monthly_data = db.session.query(
            db.func.month(Payment.payment_date).label('month'),
            db.func.sum(Payment.amount).label('total')
        ).filter(
            Payment.student_id == student.id,
            Payment.status == 'completed',
            db.func.year(Payment.payment_date) == current_year
        ).group_by(
            db.func.month(Payment.payment_date)
        ).all()

        months_map = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
            5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
            9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }

        chart_labels = [months_map[row.month] for row in monthly_data]
        chart_amounts = [float(row.total) for row in monthly_data]

        student_info.append({
            'student': student,
            'total_fees': total_fees,
            'total_paid': total_paid,
            'balance': balance,
            'payment_percentage': payment_percentage,
            'due_date': due_date,
            'is_overdue': is_overdue,
            'recent_payments': paginated_payments,
            'current_page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_page': page - 1,
            'next_page': page + 1,
            'chart_labels': json.dumps(chart_labels),
            'chart_amounts': json.dumps(chart_amounts),
        })

    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(10).all()

    return render_template(
        'parent_dashboard.html',
        parent=parent,
        student_info=student_info,
        notifications=notifications,
        current_term=current_term,
        current_year=current_year
    )

@app.route('/parent/payments/<int:student_id>')
@login_required
def parent_payment_history(student_id):
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    if not parent:
        flash('No parent profile found.', 'danger')
        return redirect(url_for('login'))

    student = db.session.get(Student, student_id)
    if not student:
        flash('Student not found.', 'danger')
        return redirect(url_for('parent_dashboard'))

    if student not in parent.students:
        flash('Access denied. This is not your child.', 'danger')
        return redirect(url_for('parent_dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = 10

    all_payments = Payment.query.filter_by(
        student_id=student.id
    ).order_by(Payment.payment_date.desc()).all()

    total = len(all_payments)
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    paginated_payments = all_payments[start:start + per_page]

    total_paid = sum(
        float(p.amount) for p in all_payments
        if p.status == 'completed'
    )

    return render_template(
        'parent_payment_history.html',
        student=student,
        payments=paginated_payments,
        total_paid=total_paid,
        current_page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_page=page - 1,
        next_page=page + 1
    )


@app.route('/parent/fees/<int:student_id>')
@login_required
def parent_fee_details(student_id):
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    if not parent:
        flash('No parent profile found.', 'danger')
        return redirect(url_for('login'))

    student = db.session.get(Student, student_id)
    if not student:
        abort(404)

    if student not in parent.students:
        flash('Access denied. This is not your child.', 'danger')
        return redirect(url_for('parent_dashboard'))

    current_year = datetime.now().year
    fee_structures = FeeStructure.query.filter_by(
        class_id=student.class_id,
        year=current_year
    ).order_by(FeeStructure.term).all()

    total_paid = db.session.query(
        db.func.coalesce(db.func.sum(Payment.amount), 0)
    ).filter_by(
        student_id=student.id,
        status='completed'
    ).scalar() or 0

    total_fees = sum(float(f.amount) for f in fee_structures)
    balance = total_fees - float(total_paid)

    return render_template(
        'parent_fee_details.html',
        student=student,
        fee_structures=fee_structures,
        total_fees=total_fees,
        total_paid=total_paid,
        balance=balance,
        datetime=datetime
    )

@app.route('/parent/notifications')
@login_required
def parent_notifications():
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    unread = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).all()

    for n in unread:
        n.is_read = True
    db.session.commit()

    return render_template(
        'parent_notifications.html',
        notifications=notifications
    )

@app.route('/parent/invoices')
@login_required
def parent_invoices():
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    if not parent:
        flash('No parent profile found.', 'danger')
        return redirect(url_for('login'))

    student_ids = [s.id for s in parent.students]
    invoices = Invoice.query.filter(
        Invoice.student_id.in_(student_ids)
    ).order_by(Invoice.created_at.desc()).all()

    return render_template('invoices_parent.html', invoices=invoices)

@app.route('/parent/invoices/<int:invoice_id>')
@login_required
def parent_view_invoice(invoice_id):
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    if not parent:
        flash('No parent profile found.', 'danger')
        return redirect(url_for('login'))

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        abort(404)

    student_ids = [s.id for s in parent.students]
    if invoice.student_id not in student_ids:
        flash('Access denied.', 'danger')
        return redirect(url_for('parent_invoices'))

    return render_template('invoices_parent_detail.html', invoice=invoice)

# ======================== M-Pesa Routes =========================
@app.route('/pay/mpesa/<int:student_id>', methods=['POST'])
@login_required
def initiate_mpesa(student_id):
    if current_user.role != 'parent':
        return {'error': 'Unauthorized'}, 403

    student = db.session.get(Student, student_id)
    if not student:
        abort(404)

    amount = request.form.get('amount', type=int)
    phone = request.form.get('phone') or getattr(current_user, 'phone_number', None)

    if not amount or amount < 1:
        flash('Enter a valid amount.', 'danger')
        return redirect(url_for('parent_dashboard'))

    if not phone:
        flash('No phone number on file. Contact admin.', 'danger')
        return redirect(url_for('parent_dashboard'))

    try:
        result = stk_push(
            phone_number=phone,
            amount=amount,
            account_ref=student.admission_number,
            description='School Fees - ShulePay'
        )

        if result.get('ResponseCode') == '0':
            mpesa_req = MpesaRequest(
                student_id=student.id,
                phone_number=phone,
                amount=amount,
                checkout_request_id=result.get('CheckoutRequestID'),
                merchant_request_id=result.get('MerchantRequestID'),
                status='pending'
            )
            db.session.add(mpesa_req)
            db.session.commit()
            flash(
                f'✅ M-Pesa prompt sent to {phone}. Enter your PIN to complete payment.',
                'success'
            )
        else:
            flash(
                f'M-Pesa error: {result.get("CustomerMessage", "Try again.")}',
                'danger'
            )

    except Exception as e:
        flash(f'Could not reach M-Pesa. Please try again. ({str(e)})', 'danger')

    return redirect(url_for('parent_dashboard'))

@app.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    data = request.get_json(silent=True) or {}

    try:
        body = data.get('Body', {}).get('stkCallback', {})
        checkout_request_id = body.get('CheckoutRequestID')
        result_code = body.get('ResultCode')
        result_desc = body.get('ResultDesc')

        mpesa_req = MpesaRequest.query.filter_by(
            checkout_request_id=checkout_request_id
        ).first()

        if not mpesa_req:
            return {'ResultCode': 0, 'ResultDesc': 'Accepted'}, 200

        if result_code == 0:
            items = body.get('CallbackMetadata', {}).get('Item', [])
            meta = {item['Name']: item.get('Value') for item in items}

            mpesa_req.status = 'completed'
            mpesa_req.mpesa_code = meta.get('MpesaReceiptNumber')
            mpesa_req.result_desc = result_desc

            payment = Payment(
                student_id=mpesa_req.student_id,
                school_id=Student.query.get(mpesa_req.student_id).school_id,
                amount=mpesa_req.amount,
                payment_method='M-Pesa',
                payment_date=datetime.utcnow(),
                reference=mpesa_req.mpesa_code,
                status='completed'
            )
            db.session.add(payment)

            student = db.session.get(Student, mpesa_req.student_id)
            if student:
                for parent in student.parents:
                    if parent.user:
                        notification = Notification(
                            user_id=parent.user.id,
                            title='✅ M-Pesa Payment Received',
                            message=(
                                f'Payment of KSh {mpesa_req.amount:,.0f} received. '
                                f'M-Pesa code: {mpesa_req.mpesa_code}'
                            ),
                            notification_type='payment_confirmed',
                            is_read=False
                        )
                        db.session.add(notification)
        else:
            mpesa_req.status = 'failed'
            mpesa_req.result_desc = result_desc

        db.session.commit()

    except Exception as e:
        app.logger.error(f'Callback error: {e}')

    return {'ResultCode': 0, 'ResultDesc': 'Accepted'}, 200

# ========================= Notification Routes =========================
@app.route('/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.filter_by(
        id=notif_id,
        user_id=current_user.id
    ).first_or_404()
    notif.is_read = True
    db.session.commit()
    return {'status': 'ok'}, 200

@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return {'status': 'ok'}, 200

# ========================= AJAX Routes =========================
@app.route('/payments/ajax')
@login_required
def payments_ajax():
    if current_user.role != 'parent':
        return {'error': 'Unauthorized'}, 403

    student_id = request.args.get('student_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 5

    parent = current_user.parent_profile
    student = db.session.get(Student, student_id)
    if not student:
        return {'error': 'Not found'}, 404

    if student not in parent.students:
        return {'error': 'Forbidden'}, 403

    all_payments = Payment.query.filter_by(
        student_id=student_id
    ).order_by(Payment.payment_date.desc()).all()

    total = len(all_payments)
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    payments_page = all_payments[start:start + per_page]

    return {
        'payments': [
            {
                'id': p.id,
                'date': p.payment_date.strftime('%d %b %Y'),
                'amount': float(p.amount),
                'method': p.payment_method,
                'status': p.status,
                'reference': p.reference or '',
                'term': p.term or '',
            }
            for p in payments_page
        ],
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_page': page - 1,
            'next_page': page + 1,
        }
    }, 200

# ========================= Statement Route =========================
@app.route('/fees/statement/<int:student_id>')
@login_required
def download_statement(student_id):
    if current_user.role != 'parent':
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))

    parent = current_user.parent_profile
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)

    if student not in parent.students:
        flash('Access denied.', 'danger')
        return redirect(url_for('parent_dashboard'))

    student_class = db.session.get(Classes, student.class_id)

    fee_structures = FeeStructure.query.filter_by(
        class_id=student.class_id
    ).order_by(FeeStructure.year.desc(), FeeStructure.term).all()

    payments = Payment.query.filter_by(
        student_id=student_id
    ).order_by(Payment.payment_date.desc()).all()

    total_fees = sum(float(f.amount) for f in fee_structures)
    total_paid = sum(
        float(p.amount) for p in payments
        if p.status == 'completed'
    )
    balance = total_fees - total_paid

    overdue_count = len([
        f for f in fee_structures
        if f.due_date and f.due_date < datetime.now()
    ])

    return render_template(
        'statement.html',
        student=student,
        student_class=student_class,
        fee_structures=fee_structures,
        payments=payments,
        parent=parent,
        total_fees=total_fees,
        total_paid=total_paid,
        balance=balance,
        overdue_count=overdue_count
    )

if __name__ == '__main__':
    app.run(debug=True)

