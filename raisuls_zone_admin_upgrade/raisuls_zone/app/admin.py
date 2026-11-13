from datetime import datetime, timedelta
from io import BytesIO
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user
from sqlalchemy import func
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from app import db
from app.models import Product, Category, Order, User, OrderItem, Coupon, AdminActivity, AdminNotification

admin = Blueprint("admin", __name__)
STATUSES = {"Pending", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"}

def admin_required():
    if not current_user.is_authenticated or current_user.role != "admin": abort(403)

def log_action(action, details=''):
    db.session.add(AdminActivity(actor_id=current_user.id, action=action, details=details))

def workbook_response(filename, headers, rows):
    wb = Workbook(); ws = wb.active; ws.title = 'Export'
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='172C27')
        c.alignment = Alignment(horizontal='center')
    for row in rows:
        safe = []
        for value in row:
            if isinstance(value, str) and value.startswith(('=', '+', '-', '@')): value = "'" + value
            safe.append(value)
        ws.append(safe)
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        letter = col[0].column_letter
        ws.column_dimensions[letter].width = min(max(max(len(str(c.value or '')) for c in col) + 2, 12), 42)
    output = BytesIO(); wb.save(output); output.seek(0)
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@admin.route('/')
@login_required
def dashboard():
    admin_required()
    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    low_stock = Product.query.filter(Product.active.is_(True), Product.stock <= 5).order_by(Product.stock.asc()).all()
    unread = AdminNotification.query.filter_by(is_read=False).count()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.created_at >= month_start, Order.status != 'Cancelled').scalar()
    best_sellers = db.session.query(OrderItem.product_name, func.sum(OrderItem.quantity).label('sold')).group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    return render_template('admin.html', products=Product.query.count(), orders=len(all_orders),
        customers=User.query.filter_by(role='customer').count(),
        revenue=sum((Decimal(str(o.total)) for o in all_orders if o.status != 'Cancelled'), Decimal('0')),
        month_revenue=month_revenue, recent_orders=all_orders[:8], low_stock=low_stock,
        best_sellers=best_sellers, unread=unread, notifications=AdminNotification.query.order_by(AdminNotification.created_at.desc()).limit(6).all())

@admin.route('/products', methods=['GET','POST'])
@login_required
def products():
    admin_required()
    if request.method == 'POST':
        name=request.form.get('name','').strip(); desc=request.form.get('description','').strip()
        price=request.form.get('price', type=Decimal); stock=request.form.get('stock', type=int); cat=request.form.get('category_id', type=int)
        category = db.session.get(Category, cat) if cat else None
        image_url=request.form.get('image_url','').strip()
        if not name or price is None or not price.is_finite() or price < 0 or stock is None or stock < 0 or (cat and not category):
            flash('Check the product name, price, stock and category.','error')
        elif len(image_url) > 500:
            flash('Image URL is too long.','error')
        else:
            try:
                p=Product(name=name, description=desc, price=price, stock=stock, category_id=cat or None, image_url=image_url)
                db.session.add(p); log_action('Product created', name); db.session.commit(); flash('Product created.','success')
            except Exception:
                db.session.rollback(); flash('Product could not be created. Please try again.','error')
        return redirect(url_for('admin.products'))
    query=Product.query
    search=request.args.get('q','').strip()
    status=request.args.get('status','')
    category_id=request.args.get('category',type=int)
    if search:
        query=query.filter(Product.name.ilike(f'%{search}%'))
    if status == 'active': query=query.filter_by(active=True)
    elif status == 'hidden': query=query.filter_by(active=False)
    if category_id: query=query.filter_by(category_id=category_id)
    page=max(request.args.get('page',1,type=int),1)
    pagination=query.order_by(Product.id.desc()).paginate(page=page,per_page=12,error_out=False)
    return render_template('admin_products.html', products=pagination.items, pagination=pagination,
        categories=Category.query.order_by(Category.name.asc()).all(), search=search, selected_status=status,
        selected_category=category_id)

def _delete_product_records(product):
    # Preserve historical order line snapshots while detaching the deleted catalogue item.
    from app.models import CartItem
    CartItem.query.filter_by(product_id=product.id).delete(synchronize_session=False)
    OrderItem.query.filter_by(product_id=product.id).update({OrderItem.product_id: None}, synchronize_session=False)
    name=product.name
    db.session.delete(product)
    return name

@admin.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    admin_required()
    product=Product.query.get_or_404(product_id)
    try:
        name=_delete_product_records(product)
        log_action('Product deleted', name)
        db.session.commit()
        flash(f'"{name}" was deleted. Historical order details were preserved.','success')
    except Exception:
        db.session.rollback(); flash('Product could not be deleted. No changes were saved.','error')
    return redirect(url_for('admin.products'))

@admin.route('/products/<int:product_id>/duplicate', methods=['POST'])
@login_required
def duplicate_product(product_id):
    admin_required(); source=Product.query.get_or_404(product_id)
    try:
        copy=Product(name=f'{source.name} (Copy)'[:160], description=source.description,
            price=source.price, stock=0, image_url=source.image_url,
            category_id=source.category_id, active=False)
        db.session.add(copy); log_action('Product duplicated', f'{source.name} → {copy.name}')
        db.session.commit(); flash('Product duplicated as a hidden draft with zero stock.','success')
    except Exception:
        db.session.rollback(); flash('Product could not be duplicated.','error')
    return redirect(url_for('admin.products'))

@admin.route('/products/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_products():
    admin_required()
    ids=[]
    for raw in request.form.getlist('product_ids'):
        try: ids.append(int(raw))
        except (TypeError, ValueError): continue
    if not ids:
        flash('Select at least one product.','error')
        return redirect(url_for('admin.products'))
    try:
        selected=Product.query.filter(Product.id.in_(set(ids))).all()
        names=[_delete_product_records(p) for p in selected]
        log_action('Bulk product deletion', f'{len(names)} product(s): {", ".join(names[:20])}')
        db.session.commit()
        flash(f'{len(names)} product(s) deleted. Historical order details were preserved.','success')
    except Exception:
        db.session.rollback(); flash('Bulk deletion failed. No products were deleted.','error')
    return redirect(url_for('admin.products'))

@admin.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
def edit_product(product_id):
    admin_required(); p=Product.query.get_or_404(product_id)
    name=request.form.get('name','').strip(); price=request.form.get('price',type=float); stock=request.form.get('stock',type=int)
    if not name or price is None or price < 0 or stock is None or stock < 0:
        flash('Invalid product values.','error')
    else:
        p.name=name; p.description=request.form.get('description','').strip(); p.price=price; p.stock=stock
        p.category_id=request.form.get('category_id',type=int) or None
        p.image_url=request.form.get('image_url','').strip(); p.active=bool(request.form.get('active'))
        log_action('Product updated', p.name); db.session.commit(); flash('Product updated.','success')
    return redirect(url_for('admin.products'))

@admin.route('/orders')
@login_required
def orders():
    admin_required(); status=request.args.get('status',''); search=request.args.get('q','').strip()
    query=Order.query
    if status in STATUSES: query=query.filter_by(status=status)
    if search:
        if search.isdigit(): query=query.filter((Order.id == int(search)) | Order.customer_name.ilike(f'%{search}%') | Order.phone.ilike(f'%{search}%'))
        else: query=query.filter(Order.customer_name.ilike(f'%{search}%') | Order.phone.ilike(f'%{search}%'))
    return render_template('admin_orders.html', orders=query.order_by(Order.created_at.desc()).all(), statuses=sorted(STATUSES), selected=status, search=search)

@admin.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_order(order_id):
    admin_required(); order=Order.query.get_or_404(order_id); status=request.form.get('status')
    if status in STATUSES:
        old=order.status
        # Restore inventory exactly once on cancellation; reserve it again if reopened.
        if status == 'Cancelled' and old != 'Cancelled':
            for line in order.items:
                product = db.session.get(Product, line.product_id) if line.product_id else None
                if product: product.stock += line.quantity
        elif old == 'Cancelled' and status != 'Cancelled':
            shortages = [line.product_name for line in order.items
                         if line.product_id and db.session.get(Product, line.product_id)
                         and db.session.get(Product, line.product_id).stock < line.quantity]
            if shortages:
                flash('Cannot reopen this order: stock is insufficient for ' + ', '.join(shortages), 'error')
                return redirect(request.referrer or url_for('admin.orders'))
            for line in order.items:
                product = db.session.get(Product, line.product_id) if line.product_id else None
                if product: product.stock -= line.quantity
        order.status=status
        db.session.add(AdminNotification(title=f'Order #{order.id} updated', message=f'{old} → {status} for {order.customer_name}', kind='order'))
        log_action('Order status changed', f'#{order.id}: {old} → {status}'); db.session.commit(); flash('Order status updated.','success')
    return redirect(request.referrer or url_for('admin.orders'))

@admin.route('/customers')
@login_required
def customers():
    admin_required(); people=User.query.filter_by(role='customer').order_by(User.created_at.desc()).all()
    return render_template('admin_customers.html', customers=people)

@admin.route('/coupons', methods=['GET','POST'])
@login_required
def coupons():
    admin_required()
    if request.method == 'POST':
        code=request.form.get('code','').strip().upper(); discount=request.form.get('discount',type=int)
        if code and discount and 1 <= discount <= 90 and not Coupon.query.filter_by(code=code).first():
            db.session.add(Coupon(code=code,discount_percent=discount)); log_action('Coupon created',code); db.session.commit(); flash('Coupon created.','success')
        else: flash('Use a unique code and discount from 1–90%.','error')
    return render_template('admin_coupons.html', coupons=Coupon.query.order_by(Coupon.created_at.desc()).all())

@admin.route('/coupons/<int:coupon_id>/toggle', methods=['POST'])
@login_required
def toggle_coupon(coupon_id):
    admin_required(); c=Coupon.query.get_or_404(coupon_id); c.active=not c.active; log_action('Coupon toggled',c.code); db.session.commit(); return redirect(url_for('admin.coupons'))

@admin.route('/automations/run', methods=['POST'])
@login_required
def run_automations():
    admin_required(); created=0
    for p in Product.query.filter(Product.active.is_(True), Product.stock <= 5).all():
        exists=AdminNotification.query.filter_by(title=f'Low stock: {p.name}', is_read=False).first()
        if not exists:
            db.session.add(AdminNotification(title=f'Low stock: {p.name}', message=f'Only {p.stock} unit(s) remain. Reorder or update inventory.', kind='warning')); created+=1
    pending=Order.query.filter_by(status='Pending').count()
    db.session.add(AdminNotification(title='Daily store check completed', message=f'Low-stock alerts created: {created}. Pending orders: {pending}.', kind='automation'))
    log_action('Automation run',f'{created} low-stock alerts; {pending} pending orders'); db.session.commit()
    flash(f'Automation completed. {created} new low-stock alert(s); {pending} pending order(s).','success')
    return redirect(url_for('admin.dashboard'))

@admin.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def read_notification(notification_id):
    admin_required(); n=AdminNotification.query.get_or_404(notification_id); n.is_read=True; db.session.commit(); return redirect(url_for('admin.dashboard'))

@admin.route('/activity')
@login_required
def activity():
    admin_required(); return render_template('admin_activity.html', activities=AdminActivity.query.order_by(AdminActivity.created_at.desc()).limit(100).all())

@admin.route('/export/<kind>')
@login_required
def export(kind):
    admin_required()
    if kind == 'orders':
        rows=((o.id,o.customer_name,o.phone,o.address,float(o.total),o.status,o.payment_method,o.created_at.strftime('%Y-%m-%d %H:%M')) for o in Order.query.order_by(Order.id.desc()).all())
        return workbook_response('raisuls-zone-orders.xlsx',['Order ID','Customer','Phone','Address','Total BDT','Status','Payment','Created'],rows)
    if kind == 'products':
        rows=((p.id,p.name,p.category.name if p.category else '',float(p.price),p.stock,'Active' if p.active else 'Hidden') for p in Product.query.order_by(Product.id.desc()).all())
        return workbook_response('raisuls-zone-products.xlsx',['Product ID','Name','Category','Price BDT','Stock','Visibility'],rows)
    if kind == 'customers':
        rows=((u.id,u.name,u.email,u.created_at.strftime('%Y-%m-%d')) for u in User.query.filter_by(role='customer').all())
        return workbook_response('raisuls-zone-customers.xlsx',['Customer ID','Name','Email','Joined'],rows)
    abort(404)
