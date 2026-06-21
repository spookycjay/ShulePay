from app import app
from models import db, User, Student, Classes, Parent, FeeStructure, Payment, Receipt, Expense, Notification, Analytics

with app.app_context():
    print("--- 1. Clearing old data ---")
    db.drop_all()
    
    print("--- 2. Building ALL 11 Tables ---")
    db.create_all()
    
    print("--- 3. Setting up Admin Account ---")
    admin = User(username='admin', email='admin@shulepay.com', role='admin')
    admin.set_password('admin123')
    
    db.session.add(admin)
    db.session.commit()
    
    print("\n ALL 11 TABLES ARE NOW IN THE DATABASE!")