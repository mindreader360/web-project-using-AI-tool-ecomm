# RAISUL'S ZONE — upgraded Flask e-commerce MVP

A responsive Flask + HTML/CSS storefront with a more capable admin workspace. It uses SQLAlchemy and SQLite by default and can be pointed at PostgreSQL with `DATABASE_URL`.

## Requirements and local setup
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`
- Copy `.env.example` to `.env`, then set a long random `SECRET_KEY`.
- Start: `python run.py`
- Open `http://127.0.0.1:5000`
- Create the first administrator in another terminal: `python seed_admin.py`

## Admin access
Sign in at `/auth/login` with the admin credentials. Admin workspace includes:
- Store dashboard with all-time and current-month revenue, order/customer/product totals
- Recent order management and status filtering
- Product creation and editing, visibility toggle, stock and image URL fields
- Low-stock inventory watch and in-app notification centre
- Smart automation runner: scans low-stock inventory and pending orders, creates alerts, and writes an audit entry
- Optional scheduled low-stock scan every six hours (`ENABLE_SCHEDULER=true`)
- Customer directory and Excel exports for orders, products and customers
- Coupon creation and activation/pause controls
- Admin activity/audit log
- Excel workbooks include headers, filters, frozen header row and readable column widths

## Scheduled automation
Set `ENABLE_SCHEDULER=true` to run the low-stock scan every six hours. Run exactly one scheduler instance for the deployment (do not enable it independently in every Gunicorn/uWSGI worker). For multi-worker production, move scheduled jobs to a dedicated worker/process. The automation currently creates in-app alerts; it does not send email, SMS or WhatsApp messages until a provider is configured.

## Important implementation notes
- Excel exports are generated with `openpyxl` and escape formula-like text cells.
- Customer checkout remains Cash on Delivery in this version.
- Coupons can be created and managed in the admin panel, but coupon redemption is not yet connected to checkout.
- Payment gateway, SMS OTP, courier APIs, email/WhatsApp notifications, image upload storage, reviews, wishlist, seller portal and AI recommendations require credentials or additional implementation; they are not simulated as live integrations.
- `db.create_all()` creates new tables but does not migrate existing table schemas. For an existing database, use a tested backup and migration plan before deploying schema changes. For production, add Flask-Migrate/Alembic, PostgreSQL, HTTPS, secure cookies, rate limiting, backups, monitoring and a production WSGI server.

## Project structure
```text
app/
  __init__.py
  models.py
  auth.py
  routes.py
  admin.py
  templates/
  static/css/style.css
run.py
seed_admin.py
config.py
requirements.txt
```


## Admin workspace upgrade (November 2026)

The product workspace now includes:
- Product search, visibility and category filters, with server-side pagination.
- Create and edit validation for product name, price, stock and category.
- Individual deletion and bulk deletion with confirmation.
- Safe catalogue deletion: cart rows are removed, while historical order-line names/prices/quantities remain and their optional product reference is detached.
- Product duplication as a hidden draft with zero stock, so a copy cannot accidentally become purchasable.
- Order search by order ID, customer name or phone, plus the Returned status.
- Admin appearance controls for System / Light / Dark mode and a custom accent color. Preferences are stored in that browser's local storage and applied across storefront/admin pages.

### Upgrade safety and verification notes
- No database schema migration is required for this update.
- Existing database rows are not mass-edited. A product deletion only changes related cart/order-line references as described above.
- Python source compilation and Jinja template syntax checks passed in the build environment.
- Full Flask/database/browser workflow tests were not run in the build environment because Flask and Flask-SQLAlchemy are not installed there. Install `requirements.txt`, back up your database, then verify create/edit/duplicate/delete and order history on a staging copy before production deployment.
- The accent/theme preferences are browser-local (not shared between administrators or devices). A database-backed global store theme editor is not part of this update.
- Product image fields continue to accept image URLs; secure local image upload, SKU/barcode, product variants, role-based permissions, AI integrations, PDF invoices, and database backup/restore remain future work rather than simulated features.
