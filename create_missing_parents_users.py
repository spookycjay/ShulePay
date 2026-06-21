from app import app
from extension import db
from models import User, Parent


DEFAULT_PASSWORD = "parent123"


def generate_unique_username(first_name, last_name):
    base_username = f"{first_name}.{last_name}".lower().replace(" ", "")
    username = base_username
    counter = 1

    while User.query.filter_by(username=username).first():
        username = f"{base_username}{counter}"
        counter += 1

    return username


with app.app_context():
    parents = Parent.query.all()

    if not parents:
        print("No parents found in the database.")

    for parent in parents:
        print(f"Checking parent: {parent.first_name} {parent.last_name} - {parent.email}")

        user = User.query.filter_by(email=parent.email).first()

        if not user:
            username = generate_unique_username(parent.first_name, parent.last_name)

            user = User(
                username=username,
                email=parent.email,
                role="parent"
            )
            user.set_password(DEFAULT_PASSWORD)

            db.session.add(user)
            db.session.flush()

            print(f"Created user account for {parent.email}")
        else:
            print(f"User account already exists for {parent.email}")

            if user.role != "parent":
                user.role = "parent"
                print(f"Updated user role to parent for {parent.email}")

        parent.user_id = user.id

        print(f"Linked Parent ID {parent.id} to User ID {user.id}")

    db.session.commit()

    print("Done creating/linking parent users.")