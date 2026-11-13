from app import create_app, db
from app.models import User
import getpass

app = create_app()
with app.app_context():
    email = input("Admin email: ").strip().lower()
    name = input("Admin name: ").strip()
    password = getpass.getpass("Admin password (8+ chars): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if User.query.filter_by(email=email).first():
        raise SystemExit("That email already exists.")
    user = User(name=name, email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print("Admin created. Sign in at /auth/login")
