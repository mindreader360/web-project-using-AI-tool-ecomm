from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Product, Category, CartItem, Order, OrderItem

main = Blueprint("main", __name__)

@main.route("/")
def index():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    query = Product.query.filter_by(active=True)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter_by(category_id=category_id)
    sort = request.args.get("sort")
    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())
    products = query.all()
    return render_template("index.html", products=products, categories=Category.query.all(), q=q)

@main.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()
    return render_template("product.html", product=product)

@main.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum((Decimal(str(i.product.price)) * i.quantity for i in items), Decimal("0.00"))
    return render_template("cart.html", items=items, total=total)

@main.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    if product.stock < 1:
        flash("This product is out of stock.", "error")
    else:
        item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
        if item:
            if item.quantity < product.stock:
                item.quantity += 1
        else:
            db.session.add(CartItem(user_id=current_user.id, product_id=product.id, quantity=1))
        db.session.commit()
        flash("Added to cart.", "success")
    return redirect(request.referrer or url_for("main.index"))

@main.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_cart(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    qty = request.form.get("quantity", type=int)
    if qty is None or qty <= 0:
        db.session.delete(item)
    elif qty <= item.product.stock:
        item.quantity = qty
    else:
        flash("Requested quantity exceeds available stock.", "error")
    db.session.commit()
    return redirect(url_for("main.cart"))

@main.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        return redirect(url_for("main.cart"))
    total = sum((Decimal(str(i.product.price)) * i.quantity for i in items), Decimal("0.00"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        if not all([name, phone, address]):
            flash("Please complete all delivery details.", "error")
        elif any(i.quantity > i.product.stock for i in items):
            flash("Stock changed. Please review your cart.", "error")
        else:
            order = Order(user_id=current_user.id, customer_name=name, phone=phone,
                          address=address, total=total, payment_method="Cash on Delivery")
            db.session.add(order)
            db.session.flush()
            for item in items:
                item.product.stock -= item.quantity
                db.session.add(OrderItem(order_id=order.id, product_id=item.product_id,
                    product_name=item.product.name, unit_price=item.product.price, quantity=item.quantity))
                db.session.delete(item)
            db.session.commit()
            flash(f"Order #{order.id} placed successfully.", "success")
            return redirect(url_for("main.orders"))
    return render_template("checkout.html", items=items, total=total)

@main.route("/orders")
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("orders.html", orders=orders)
