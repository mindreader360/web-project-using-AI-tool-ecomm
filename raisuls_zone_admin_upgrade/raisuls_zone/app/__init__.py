from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"

    from app.routes import main
    from app.auth import auth
    from app.admin import admin
    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(admin, url_prefix="/admin")

    with app.app_context():
        db.create_all()
        from app.models import User, Product, Category
        if not Category.query.first():
            for name in ["Electronics", "Fashion", "Home & Living", "Beauty", "Sports"]:
                db.session.add(Category(name=name, slug=name.lower().replace(" & ", "-").replace(" ", "-")))
            db.session.commit()
        if not Product.query.first():
            cat = Category.query.first()
            samples = [
                ("Wireless Headphones", "Comfortable Bluetooth headphones with clear sound.", 1890, 20, cat.id),
                ("Smart Watch", "Fitness tracking, notifications and elegant design.", 2490, 15, cat.id),
                ("Everyday Backpack", "Durable everyday backpack with laptop compartment.", 1290, 30, cat.id),
            ]
            for name, desc, price, stock, category_id in samples:
                db.session.add(Product(name=name, description=desc, price=price, stock=stock, category_id=category_id, image_url=""))
            db.session.commit()
    if app.config.get("ENABLE_SCHEDULER"):
        # Run one scheduler process only; do not enable in every web worker.
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.models import Product, AdminNotification
        def inventory_scan():
            with app.app_context():
                for product in Product.query.filter(Product.active.is_(True), Product.stock <= 5).all():
                    existing = AdminNotification.query.filter_by(title=f"Low stock: {product.name}", is_read=False).first()
                    if not existing:
                        db.session.add(AdminNotification(title=f"Low stock: {product.name}", message=f"Only {product.stock} unit(s) remain. Reorder or update inventory.", kind="warning"))
                db.session.commit()
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(inventory_scan, "interval", hours=6, id="inventory_scan", replace_existing=True)
        scheduler.start()
        app.extensions["inventory_scheduler"] = scheduler
    return app
