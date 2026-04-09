from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
mysql = MySQL(app)


# ── Helper: fetch all categories ─────────────────────────────
# We need categories in multiple routes (add, edit, browse).
# Putting it in a helper avoids repeating the same query.
def get_categories():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM categories')
    cats = cursor.fetchall()
    cursor.close()
    return cats


# ============================================================
# Home
# ============================================================
@app.route('/')
def home():
    return render_template('home.html')


# ── Context processor ─────────────────────────────────────────
# This runs automatically before EVERY page render.
# It injects 'pending_count' into every template globally,
# so the navbar can show it without each route passing it manually.
@app.context_processor
def inject_pending_count():
    count = 0
    if session.get('user_id'):
        cursor = mysql.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) AS cnt
            FROM requests r
            JOIN products p ON r.product_id = p.product_id
            WHERE p.user_id = %s AND r.status = 'Pending'
        ''', (session['user_id'],))
        result = cursor.fetchone()
        cursor.close()
        count = result['cnt'] if result else 0
    return dict(pending_count=count)


# ============================================================
# Register
# ============================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        name             = request.form['name'].strip()
        email            = request.form['email'].strip().lower()
        phone            = request.form['phone'].strip()
        password         = request.form['password']
        confirm_password = request.form['confirm_password']

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        cursor = mysql.connection.cursor()
        cursor.execute(
            'SELECT user_id FROM users WHERE email = %s', (email,)
        )
        if cursor.fetchone():
            flash('An account with this email already exists.', 'danger')
            cursor.close()
            return redirect(url_for('register'))

        hashed = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (name, email, password, phone) VALUES (%s, %s, %s, %s)',
            (name, email, hashed, phone)
        )
        mysql.connection.commit()
        cursor.close()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# ============================================================
# Login
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))

        session['user_id']   = user['user_id']
        session['user_name'] = user['name']
        flash(f"Welcome back, {user['name']}!", 'success')
        return redirect(url_for('home'))

    return render_template('login.html')


# ============================================================
# Logout
# ============================================================
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('home'))


# ============================================================
# Browse Products + Search
# ============================================================
@app.route('/products')
def products():
    query    = request.args.get('query', '').strip()
    category = request.args.get('category', '')

    cursor = mysql.connection.cursor()

    # ── Build the SQL query dynamically based on filters ────
    # We JOIN products with users (to get seller name) and
    # categories (to get category name) — this is a 3NF benefit:
    # data lives in one place and we fetch it via JOIN.
    sql = '''
        SELECT
            p.product_id,
            p.name,
            p.description,
            p.price,
            p.status,
            p.listed_at,
            p.user_id,
            p.stock,
            u.name   AS seller_name,
            u.trust_score,
            c.category_name,
            c.category_id
        FROM products p
        JOIN users      u ON p.user_id     = u.user_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE p.status = 'Available'
    '''

    params = []

    # Append search filter if user typed something
    if query:
        sql += ' AND (p.name LIKE %s OR p.description LIKE %s)'
        params.extend([f'%{query}%', f'%{query}%'])
        # LIKE %query% means "contains this word anywhere"

    # Append category filter if user selected one
    if category:
        sql += ' AND c.category_id = %s'
        params.append(category)

    sql += ' ORDER BY p.listed_at DESC'
    # Show newest listings first

    cursor.execute(sql, params)
    all_products = cursor.fetchall()
    cursor.close()

    categories = get_categories()

    return render_template(
        'products.html',
        products=all_products,
        categories=categories
    )
    # We pass 'products' and 'categories' to the template.
    # In the HTML, {{ products }} and {{ categories }} refer to these.


# ============================================================
# Product Detail Page
# ============================================================
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT p.*, u.name AS seller_name,
               u.trust_score, c.category_name
        FROM products p
        JOIN users      u ON p.user_id     = u.user_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE p.product_id = %s
    ''', (product_id,))
    product = cursor.fetchone()

    if not product:
        flash('Product not found.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    # Check if the logged-in buyer already sent a request
    request_status = None
    if session.get('user_id'):
        cursor.execute('''
            SELECT status FROM requests
            WHERE product_id = %s AND buyer_id = %s
        ''', (product_id, session['user_id']))
        existing = cursor.fetchone()
        if existing:
            request_status = existing['status']

    cursor.close()
    return render_template(
        'product_detail.html',
        product=product,
        request_status=request_status
    )


# ============================================================
# Add Product
# ============================================================
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if not session.get('user_id'):
        flash('Please log in to list an item.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name        = request.form['name'].strip()
        category_id = request.form['category_id']
        description = request.form['description'].strip()
        price       = request.form['price']
        stock       = request.form['stock']

        if not name or not category_id or not price:
            flash('Name, category and price are required.', 'danger')
            return redirect(url_for('add_product'))

        cursor = mysql.connection.cursor()
        cursor.execute('''
        INSERT INTO products
        (user_id, category_id, name, description, price, stock)
        VALUES (%s, %s, %s, %s, %s, %s)
        ''', (session['user_id'], category_id, name, description, price, stock))
        mysql.connection.commit()
        cursor.close()

        flash('Your item has been listed!', 'success')
        return redirect(url_for('products'))

    categories = get_categories()
    return render_template('add_product.html', categories=categories)


# ============================================================
# Edit Product
# ============================================================
@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch the product first
    cursor.execute(
        'SELECT * FROM products WHERE product_id = %s', (product_id,)
    )
    product = cursor.fetchone()

    # Security check: make sure only the seller can edit their listing
    if not product or product['user_id'] != session['user_id']:
        flash('You are not allowed to edit this listing.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    if request.method == 'POST':
        name        = request.form['name'].strip()
        category_id = request.form['category_id']
        description = request.form['description'].strip()
        price       = request.form['price']
        status      = request.form['status']
        stock       = request.form['stock']        # ← added

        cursor.execute('''
            UPDATE products
            SET name=%s, category_id=%s, description=%s,
                price=%s, status=%s, stock=%s
            WHERE product_id=%s
        ''', (name, category_id, description, price, status, stock, product_id))
        mysql.connection.commit()
        cursor.close()

        flash('Listing updated successfully!', 'success')
        return redirect(url_for('profile'))

    cursor.close()
    categories = get_categories()
    return render_template(
        'edit_product.html',
        product=product,
        categories=categories
    )


# ============================================================
# Delete Product
# ============================================================
@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute(
        'SELECT * FROM products WHERE product_id = %s', (product_id,)
    )
    product = cursor.fetchone()

    # Security check: only the seller can delete their own listing
    if not product or product['user_id'] != session['user_id']:
        flash('You are not allowed to delete this listing.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    cursor.execute(
        'DELETE FROM products WHERE product_id = %s', (product_id,)
    )
    mysql.connection.commit()
    cursor.close()

    flash('Listing deleted.', 'info')
    return redirect(url_for('profile'))


# ============================================================
# Mark as Sold — ONLY the seller can do this
# ============================================================
@app.route('/mark_sold/<int:product_id>', methods=['POST'])
def mark_sold(product_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute(
        'SELECT * FROM products WHERE product_id = %s', (product_id,)
    )
    product = cursor.fetchone()

    if not product:
        flash('Product not found.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    # ── KEY CHECK: only the seller can mark their item sold ──
    if product['user_id'] != session['user_id']:
        flash('Only the seller can mark an item as sold.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    if product['status'] == 'Sold':
        flash('This item is already marked as sold.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    # Mark as sold
    cursor.execute(
        'UPDATE products SET status = %s WHERE product_id = %s',
        ('Sold', product_id)
    )

    # Record the transaction with no specific buyer (NULL)
    # because contact happened outside the platform
    cursor.execute(
        'INSERT INTO transactions (buyer_id, product_id) VALUES (NULL, %s)',
        (product_id,)
    )

    # Increase seller's own trust score
    cursor.execute(
        'UPDATE users SET trust_score = trust_score + 1 WHERE user_id = %s',
        (session['user_id'],)
    )

    mysql.connection.commit()
    cursor.close()

    flash('Item marked as sold. Trust score updated!', 'success')
    return redirect(url_for('profile'))

# ============================================================
# Profile
# ============================================================
@app.route('/profile')
def profile():
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Get user details
    cursor.execute(
        'SELECT * FROM users WHERE user_id = %s', (session['user_id'],)
    )
    user = cursor.fetchone()

    # Get all listings by this user (with category name via JOIN)
    cursor.execute('''
        SELECT p.*, c.category_name
        FROM products p
        JOIN categories c ON p.category_id = c.category_id
        WHERE p.user_id = %s
        ORDER BY p.listed_at DESC
    ''', (session['user_id'],))
    listings = cursor.fetchall()
    cursor.close()

    return render_template('profile.html', user=user, listings=listings)



# ============================================================
# Request Interest — buyer clicks "I'm Interested"
# ============================================================
@app.route('/request_interest/<int:product_id>', methods=['POST'])
def request_interest(product_id):
    if not session.get('user_id'):
        flash('Please log in to show interest.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch the product
    cursor.execute(
        'SELECT * FROM products WHERE product_id = %s', (product_id,)
    )
    product = cursor.fetchone()

    if not product:
        flash('Product not found.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    if product['status'] == 'Sold':
        flash('This item is no longer available.', 'danger')
        cursor.close()
        return redirect(url_for('products'))

    # Seller cannot send interest in their own listing
    if product['user_id'] == session['user_id']:
        flash("You can't send a request for your own listing.", 'danger')
        cursor.close()
        return redirect(url_for('product_detail', product_id=product_id))

    # Check if buyer already sent a request for this product
    cursor.execute('''
        SELECT request_id, status FROM requests
        WHERE product_id = %s AND buyer_id = %s
    ''', (product_id, session['user_id']))
    existing = cursor.fetchone()

    if existing:
        if existing['status'] in ['Rejected', 'Completed']:
            quantity = int(request.form.get('quantity', 1))

            if quantity < 1:
                flash('Quantity must be at least 1.', 'danger')
                cursor.close()
                return redirect(url_for('product_detail', product_id=product_id))

            if quantity > product['stock']:
                flash(f"Only {product['stock']} unit(s) available.", 'danger')
                cursor.close()
                return redirect(url_for('product_detail', product_id=product_id))

            # Reset the existing request back to Pending with new quantity
            cursor.execute('''
                UPDATE requests SET status = 'Pending', quantity = %s
                WHERE product_id = %s AND buyer_id = %s
            ''', (quantity, product_id, session['user_id']))
            mysql.connection.commit()
            cursor.close()
            flash('Your interest has been re-sent to the seller!', 'success')
            return redirect(url_for('product_detail', product_id=product_id))
        else:
            flash('You have already sent a request for this item.', 'danger')
            cursor.close()
            return redirect(url_for('product_detail', product_id=product_id))

    # Create the request
    # Read quantity from form, default to 1
    quantity = int(request.form.get('quantity', 1))

    # Validate quantity doesn't exceed available stock
    if quantity < 1:
        flash('Quantity must be at least 1.', 'danger')
        cursor.close()
        return redirect(url_for('product_detail', product_id=product_id))

    if quantity > product['stock']:
        flash(f"Only {product['stock']} unit(s) available.", 'danger')
        cursor.close()
        return redirect(url_for('product_detail', product_id=product_id))

    # Create the request with quantity
    cursor.execute('''
        INSERT INTO requests (product_id, buyer_id, quantity)
        VALUES (%s, %s, %s)
    ''', (product_id, session['user_id'], quantity))

    mysql.connection.commit()
    cursor.close()

    flash('Your interest has been sent to the seller!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


# ============================================================
# View Requests — seller sees all requests for their listings
# ============================================================
@app.route('/requests')
def view_requests():
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch all requests for products owned by this seller
    # JOIN brings in buyer name, product name, category name
    cursor.execute('''
        SELECT
            r.request_id,
            r.status,
            r.requested_at,
            r.product_id,
            r.quantity,
            u.name      AS buyer_name,
            u.phone     AS buyer_phone,
            p.name      AS product_name,
            p.price,
            p.stock,
            p.status    AS product_status,
            c.category_name
        FROM requests r
        JOIN users      u ON r.buyer_id    = u.user_id
        JOIN products   p ON r.product_id  = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE p.user_id = %s
        ORDER BY r.requested_at DESC
    ''', (session['user_id'],))

    all_requests = cursor.fetchall()

    # ── Group requests by product ────────────────────────────
    # We want the template to show:
    #   Product A
    #     - Request from buyer 1
    #     - Request from buyer 2
    #   Product B
    #     - Request from buyer 3
    # So we build a dictionary keyed by product_id

    grouped = {}
    for req in all_requests:
        pid = req['product_id']

        if pid not in grouped:
            # Count how many requests for this product are Accepted
            remaining = req['stock']  # stock is already decremented on each accept

            grouped[pid] = {
                'product': {
                    'name':          req['product_name'],
                    'price':         req['price'],
                    'stock':         req['stock'],
                    'status':        req['product_status'],
                    'category_name': req['category_name'],
                    'product_id':    pid
                },
                'requests':  [],
                'remaining': remaining
            }

        grouped[pid]['requests'].append(req)

    cursor.close()

    return render_template(
        'requests.html',
        grouped_requests=grouped
    )


# ============================================================
# Accept Request — seller accepts a buyer's request
# ============================================================
@app.route('/accept_request/<int:request_id>', methods=['POST'])
def accept_request(request_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch the request with product info
    cursor.execute('''
        SELECT r.*, p.stock, p.user_id AS seller_id, p.status AS product_status
        FROM requests r
        JOIN products p ON r.product_id = p.product_id
        WHERE r.request_id = %s
    ''', (request_id,))
    req = cursor.fetchone()

    if not req:
        flash('Request not found.', 'danger')
        cursor.close()
        return redirect(url_for('view_requests'))

    # Security: only the seller of the product can accept
    if req['seller_id'] != session['user_id']:
        flash('You are not authorized to accept this request.', 'danger')
        cursor.close()
        return redirect(url_for('view_requests'))

    # Count how many requests already accepted for this product
    # Check if enough stock exists for the requested quantity
    if req['stock'] <= 0:
        flash('No stock remaining for this item.', 'danger')
        cursor.close()
        return redirect(url_for('view_requests'))

    if req['quantity'] > req['stock']:
        flash(
            f"Not enough stock. Buyer requested {req['quantity']} "
            f"but only {req['stock']} remaining.",
            'danger'
        )
        cursor.close()
        return redirect(url_for('view_requests'))

    # Accept this request
    # Accept this request — status becomes Ongoing
    # so both parties know to exchange contact details
    cursor.execute('''
        UPDATE requests SET status = 'Ongoing'
        WHERE request_id = %s
    ''', (request_id,))

    # Decrease stock by the requested quantity
    cursor.execute('''
        UPDATE products SET stock = stock - %s
        WHERE product_id = %s
    ''', (req['quantity'], req['product_id']))

    # Record the transaction
    cursor.execute('''
        INSERT INTO transactions (buyer_id, product_id)
        VALUES (%s, %s)
    ''', (req['buyer_id'], req['product_id']))

    # Increase seller's trust score
    cursor.execute('''
        UPDATE users SET trust_score = trust_score + 1
        WHERE user_id = %s
    ''', (session['user_id'],))

    # ── If accepted count + 1 reaches stock, mark product Sold ──
    if req['stock'] - req['quantity'] <= 0:
        cursor.execute('''
            UPDATE products SET status = 'Sold'
            WHERE product_id = %s
        ''', (req['product_id'],))
        flash(
            'Request accepted! All stock has been allocated — '
            'item marked as Sold.',
            'success'
        )
    else:
        flash('Request accepted successfully!', 'success')

    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('view_requests'))


# ============================================================
# Reject Request — seller rejects a buyer's request
# ============================================================
@app.route('/reject_request/<int:request_id>', methods=['POST'])
def reject_request(request_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    cursor.execute('''
        SELECT r.*, p.user_id AS seller_id
        FROM requests r
        JOIN products p ON r.product_id = p.product_id
        WHERE r.request_id = %s
    ''', (request_id,))
    req = cursor.fetchone()

    if not req or req['seller_id'] != session['user_id']:
        flash('Not authorized.', 'danger')
        cursor.close()
        return redirect(url_for('view_requests'))

    # If request was Ongoing before rejection,
    # give the stock slot back to the seller
    if req['status'] == 'Ongoing':
        cursor.execute('''
            UPDATE products SET stock = stock + 1
            WHERE product_id = %s
        ''', (req['product_id'],))
        # Also reopen the product if it was marked Sold
        cursor.execute('''
            UPDATE products SET status = 'Available'
            WHERE product_id = %s AND status = 'Sold'
        ''', (req['product_id'],))

    cursor.execute('''
        UPDATE requests SET status = 'Rejected'
        WHERE request_id = %s
    ''', (request_id,))

    mysql.connection.commit()
    cursor.close()

    flash('Request rejected.', 'info')
    return redirect(url_for('view_requests'))


# ============================================================
# Transaction History
# Shows all transactions where the user was buyer OR seller
# ============================================================
@app.route('/history')
def history():
    if not session.get('user_id'):
        flash('Please log in to view your history.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # ── Items this user SOLD ─────────────────────────────────
    # We find transactions where the product belonged to this user
    # LEFT JOIN on users for buyer because buyer_id can be NULL
    cursor.execute('''
        SELECT
            t.transaction_id,
            t.date,
            p.name          AS product_name,
            p.price,
            c.category_name,
            u.name          AS buyer_name
        FROM transactions t
        JOIN products   p ON t.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        LEFT JOIN users u ON t.buyer_id   = u.user_id
        WHERE p.user_id = %s
        ORDER BY t.date DESC
    ''', (session['user_id'],))
    sold = cursor.fetchall()

    # ── Items this user BOUGHT ───────────────────────────────
    # We find transactions where buyer_id matches this user
    cursor.execute('''
        SELECT
            t.transaction_id,
            t.date,
            p.name          AS product_name,
            p.price,
            c.category_name,
            u.name          AS seller_name
        FROM transactions t
        JOIN products   p ON t.product_id  = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        JOIN users      u ON p.user_id     = u.user_id
        WHERE t.buyer_id = %s
        ORDER BY t.date DESC
    ''', (session['user_id'],))
    bought = cursor.fetchall()

    cursor.close()

    return render_template('history.html', sold=sold, bought=bought)


# ============================================================
# Buyer's Requests Page — buyer sees requests they sent
# ============================================================
@app.route('/my_requests')
def my_requests():
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch all requests this buyer has sent
    # JOIN brings in product info, seller info, category
    cursor.execute('''
        SELECT
            r.request_id,
            r.status,
            r.requested_at,
            r.quantity,
            p.product_id,
            p.name      AS product_name,
            p.price,
            p.stock,
            c.category_name,
            u.name      AS seller_name,
            u.phone     AS seller_phone
        FROM requests r
        JOIN products   p ON r.product_id  = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        JOIN users      u ON p.user_id     = u.user_id
        WHERE r.buyer_id = %s
        ORDER BY r.requested_at DESC
    ''', (session['user_id'],))

    my_reqs = cursor.fetchall()

    # Also fetch buyer's own phone to show to seller
    cursor.execute(
        'SELECT phone FROM users WHERE user_id = %s',
        (session['user_id'],)
    )
    buyer = cursor.fetchone()
    cursor.close()

    return render_template(
        'my_requests.html',
        my_requests=my_reqs,
        buyer_phone=buyer['phone']
    )


# ============================================================
# Complete Request — buyer marks the deal as done
# ============================================================
@app.route('/complete_request/<int:request_id>', methods=['POST'])
def complete_request(request_id):
    if not session.get('user_id'):
        flash('Please log in.', 'danger')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()

    # Fetch the request
    cursor.execute('''
        SELECT r.*, p.user_id AS seller_id
        FROM requests r
        JOIN products p ON r.product_id = p.product_id
        WHERE r.request_id = %s
    ''', (request_id,))
    req = cursor.fetchone()

    if not req:
        flash('Request not found.', 'danger')
        cursor.close()
        return redirect(url_for('my_requests'))

    # Security: only the buyer of this request can complete it
    if req['buyer_id'] != session['user_id']:
        flash('Not authorised.', 'danger')
        cursor.close()
        return redirect(url_for('my_requests'))

    # Must be Ongoing to be completed
    if req['status'] != 'Ongoing':
        flash('This request cannot be completed at this stage.', 'danger')
        cursor.close()
        return redirect(url_for('my_requests'))

    # Mark request as Completed
    cursor.execute('''
        UPDATE requests SET status = 'Completed'
        WHERE request_id = %s
    ''', (request_id,))

    mysql.connection.commit()
    cursor.close()

    flash('Transaction completed! Enjoy your purchase.', 'success')
    return redirect(url_for('my_requests'))






if __name__ == '__main__':
    app.run(debug=True)