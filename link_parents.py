from app import app
from extension import db
from models import User, Parent

with app.app_context():
    parents = Parent.query.all()

    for parent in parents:
        if not parent.user_id and parent.email:
            user = User.query.filter_by(email=parent.email).first()
            if user:
                parent.user_id = user.id
                print(f"Linked Parent {parent.email} -> User ID {user.id}")
            else:
                print(f"No matching user found for parent: {parent.email}")

    db.session.commit()
    print("Done linking parents.")